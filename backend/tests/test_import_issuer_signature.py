"""An imported certificate is linked to a CA only when that CA's key signed it,
and a stored row only counts as issued by a CA whose key verifies it.

Issuer DN and AKI are written by whoever built the certificate; the signature
is the one thing that ties a certificate to a key.
"""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db

IMPORT = '/api/v2/certificates/import'

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _gen():
    return ec.generate_private_key(ec.SECP256R1())


def _leaf(cn, ca_cert, signer, *, key=None, aki_from=None, days=30):
    """A leaf naming ``ca_cert`` as issuer (DN and AKI), signed by ``signer``."""
    key = key or _gen()
    now = datetime.now(timezone.utc)
    ski = ca_cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=days))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier(ski.digest, None, None), critical=False)
            .sign(signer, hashes.SHA256()))
    return cert, key


def _pem(obj):
    return obj.public_bytes(serialization.Encoding.PEM).decode()


def _kpem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


@pytest.fixture(scope='module')
def issuer(app, create_ca):
    """(id, refid, certificate, signing key) of a CA holding its key."""
    data = create_ca(cn=f'Signature Binding CA {uuid.uuid4().hex[:6]}',
                     keyUsage=['digitalSignature', 'keyCertSign', 'cRLSign'])
    with app.app_context():
        from services.hsm.ca_key_loader import get_ca_signing_key
        row = db.session.get(CA, data['id'])
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        return row.id, row.refid, cert, get_ca_signing_key(row)


def _import(auth_client, cert, key=None, **form):
    pem = _pem(cert) + (_kpem(key) if key is not None else '')
    return auth_client.post(IMPORT, data={'pem_content': pem, **form},
                            content_type='multipart/form-data')


def _rows(app, cert):
    with app.app_context():
        db.session.expire_all()
        return [(r.id, r.caref) for r in Certificate.query.filter_by(
            serial_number=str(cert.serial_number)).all()]


def _store(app, cert, caref, key=None):
    """A row put straight into the database, as an older release could have left it."""
    from security.encryption import encrypt_private_key
    with app.app_context():
        row = Certificate(
            refid=str(uuid.uuid4()), descr=cert.subject.rfc4514_string(), caref=caref,
            crt=base64.b64encode(_pem(cert).encode()).decode(),
            prv=encrypt_private_key(base64.b64encode(_kpem(key).encode()).decode()) if key else None,
            cert_type='server_cert', subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(), serial_number=str(cert.serial_number),
            valid_from=cert.not_valid_before_utc.replace(tzinfo=None),
            valid_to=cert.not_valid_after_utc.replace(tzinfo=None), source='import')
        db.session.add(row)
        db.session.commit()
        return row.id


class TestImportLinksOnlyTheSigningCa:

    def test_a_ca_named_by_id_that_did_not_sign_it_is_refused(self, app, auth_client, issuer):
        ca_id, _, ca_cert, _ = issuer
        forged, key = _leaf('forged-named.example.test', ca_cert, _gen())
        r = _import(auth_client, forged, key, ca_id=str(ca_id))
        assert r.status_code == 400, r.data
        assert 'not signed' in r.get_json()['message']
        assert _rows(app, forged) == []

    def test_an_issuer_resolved_by_aki_or_dn_that_did_not_sign_it_is_not_linked(
            self, app, auth_client, issuer):
        _, _, ca_cert, _ = issuer
        forged, key = _leaf('forged-auto.example.test', ca_cert, _gen())
        r = _import(auth_client, forged, key)
        assert r.status_code in (200, 201), r.data
        assert [caref for _, caref in _rows(app, forged)] == [None]

    def test_a_certificate_the_ca_signed_is_linked_and_renews(self, app, auth_client, issuer):
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('really-issued.example.test', ca_cert, ca_key)
        r = _import(auth_client, real, key, ca_id=str(ca_id))
        assert r.status_code in (200, 201), r.data
        [(row_id, caref)] = _rows(app, real)
        assert caref == refid
        r = auth_client.post(f'/api/v2/certificates/{row_id}/renew', json={})
        assert r.status_code in (200, 201), r.data

    def test_without_ca_id_a_certificate_the_ca_signed_is_linked(self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        real, _ = _leaf('really-issued-auto.example.test', ca_cert, ca_key)
        assert _import(auth_client, real).status_code in (200, 201)
        assert [caref for _, caref in _rows(app, real)] == [refid]

    def test_a_third_party_certificate_imports_as_before(self, app, auth_client):
        other_key = _gen()
        now = datetime.now(timezone.utc)
        other = (x509.CertificateBuilder()
                 .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Elsewhere Root')]))
                 .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Elsewhere Root')]))
                 .public_key(other_key.public_key()).serial_number(x509.random_serial_number())
                 .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=90))
                 .add_extension(x509.SubjectKeyIdentifier.from_public_key(other_key.public_key()), critical=False)
                 .sign(other_key, hashes.SHA256()))
        leaf, key = _leaf('third-party.example.test', other, other_key)
        r = _import(auth_client, leaf, key)
        assert r.status_code in (200, 201), r.data
        assert [caref for _, caref in _rows(app, leaf)] == [None]

    def test_updating_a_stored_certificate_does_not_keep_a_ca_that_did_not_sign_the_new_one(
            self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('updated-twice.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid)
        forged, _ = _leaf('updated-twice.example.test', ca_cert, _gen(), key=key)
        r = _import(auth_client, forged)
        assert r.status_code == 200, r.data
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            assert row.serial_number == str(forged.serial_number)
            assert row.caref is None

    def test_updating_with_a_named_ca_that_did_not_sign_it_is_refused(self, app, auth_client, issuer):
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('updated-named.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid)
        forged, _ = _leaf('updated-named.example.test', ca_cert, _gen(), key=key)
        r = _import(auth_client, forged, ca_id=str(ca_id))
        assert r.status_code == 400, r.data
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            assert row.serial_number == str(real.serial_number) and row.caref == refid

    def test_a_record_of_the_same_key_stays_linkable(self, app, auth_client, issuer):
        """A CA re-signed under its own key (a second record, same subject and key)."""
        _, refid, ca_cert, ca_key = issuer
        now = datetime.now(timezone.utc)
        resigned = (x509.CertificateBuilder().subject_name(ca_cert.subject).issuer_name(ca_cert.subject)
                    .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
                    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                    .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
                                   critical=False)
                    .sign(ca_key, hashes.SHA256()))
        with app.app_context():
            twin = CA(refid=str(uuid.uuid4()), descr='re-signed twin', serial=0,
                      crt=base64.b64encode(_pem(resigned).encode()).decode(),
                      subject=resigned.subject.rfc4514_string(), issuer=resigned.issuer.rfc4514_string(),
                      serial_number=str(resigned.serial_number))
            db.session.add(twin)
            db.session.commit()
            twin_id, twin_refid = twin.id, twin.refid
        real, _ = _leaf('same-key.example.test', ca_cert, ca_key)
        r = _import(auth_client, real, ca_id=str(twin_id))
        assert r.status_code in (200, 201), r.data
        assert [caref for _, caref in _rows(app, real)] == [twin_refid]
        from services.cert.issued_lookup import OK, issued_certificate_status
        with app.app_context():
            assert issued_certificate_status(db.session.get(CA, issuer[0]), real)[1] == OK

    def test_smart_import_does_not_link_an_issuer_that_did_not_sign_it(self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        forged, _ = _leaf('forged-smart.example.test', ca_cert, _gen())
        real, _ = _leaf('real-smart.example.test', ca_cert, ca_key)
        r = auth_client.post('/api/v2/import/execute', data=json.dumps({
            'content': _pem(forged) + _pem(real), 'options': {'skip_duplicates': False}}),
            content_type='application/json')
        assert r.status_code == 200, r.data
        assert [caref for _, caref in _rows(app, forged)] == [None]
        assert [caref for _, caref in _rows(app, real)] == [refid]

    def test_an_opnsense_entry_naming_a_ca_that_did_not_sign_it_is_not_linked(
            self, app, auth_client, issuer, monkeypatch):
        from api.v2 import import_opnsense
        from tests.test_opnsense_import import _Session
        _, refid, ca_cert, ca_key = issuer
        forged, _ = _leaf('forged-opn.example.test', ca_cert, _gen())
        real, _ = _leaf('real-opn.example.test', ca_cert, ca_key)
        rows = [{'uuid': str(uuid.uuid4()), 'refid': uuid.uuid4().hex[:13], 'descr': cert_descr,
                 'crt': base64.b64encode(_pem(cert).encode()).decode(), 'caref': refid}
                for cert, cert_descr in ((forged, f'opn-forged-{refid}'), (real, f'opn-real-{refid}'))]
        monkeypatch.setattr(import_opnsense, 'create_session', lambda verify_ssl=True: _Session([], rows))
        r = auth_client.post('/api/v2/import/opnsense/import', json={
            'host': '192.0.2.10', 'port': 443, 'api_key': 'k', 'api_secret': 's',
            'verify_ssl': False, 'items': []})
        assert r.status_code == 200, r.data
        assert [caref for _, caref in _rows(app, forged)] == [None]
        assert [caref for _, caref in _rows(app, real)] == [refid]

    def test_the_legacy_opnsense_service_does_not_link_it_either(self, app, issuer, monkeypatch, tmp_path):
        from services.opnsense import importer
        monkeypatch.setattr(importer, '__file__', str(tmp_path / 'services' / 'opnsense' / 'importer.py'))
        _, refid, ca_cert, ca_key = issuer
        forged, _ = _leaf('forged-legacy.example.test', ca_cert, _gen())
        real, _ = _leaf('real-legacy.example.test', ca_cert, ca_key)
        entries = [{'refid': uuid.uuid4().hex[:13], 'caref': refid, 'descr': 'legacy',
                    'crt': base64.b64encode(_pem(cert).encode()).decode(),
                    'serial_number': str(cert.serial_number)} for cert in (forged, real)]
        with app.app_context():
            assert importer.ImportMixin().import_certificates(entries)['imported'] == 2
        assert [caref for _, caref in _rows(app, forged)] == [None]
        assert [caref for _, caref in _rows(app, real)] == [refid]

    def test_the_chain_repair_task_does_not_link_it_by_aki(self, app, issuer):
        from services.ski_aki_backfill import backfill_ski_aki
        _, refid, ca_cert, ca_key = issuer
        forged, _ = _leaf('forged-backfill.example.test', ca_cert, _gen())
        real, _ = _leaf('real-backfill.example.test', ca_cert, ca_key)
        ids = []
        for cert in (forged, real):
            row_id = _store(app, cert, None)
            with app.app_context():
                row = db.session.get(Certificate, row_id)
                row.aki = ca_cert.extensions.get_extension_for_class(
                    x509.SubjectKeyIdentifier).value.digest.hex(':').upper()
                db.session.commit()
            ids.append(row_id)
        with app.app_context():
            backfill_ski_aki()
        assert [caref for _, caref in _rows(app, forged)] == [None]
        assert [caref for _, caref in _rows(app, real)] == [refid]

    def test_an_admin_mtls_import_does_not_link_a_namesake_ca(self, app, auth_client, issuer):
        _, _, ca_cert, _ = issuer
        forged, _ = _leaf('forged-mtls.example.test', ca_cert, _gen())
        with app.app_context():
            from models import User
            admin_id = User.query.filter_by(username='admin').first().id
        try:
            r = auth_client.post(f'/api/v2/users/{admin_id}/mtls/certificates',
                                 json={'mode': 'import', 'pem': _pem(forged)})
            assert r.status_code in (200, 201), r.data
            assert [caref for _, caref in _rows(app, forged)] == [None]
        finally:
            from models.auth_certificate import AuthCertificate
            with app.app_context():
                AuthCertificate.query.filter_by(cert_serial=str(forged.serial_number)).delete()
                db.session.commit()


class TestStoredRowsAreIssuedOnlyWhenTheCaSignedThem:
    """Rows already in the database, linked to a CA that never signed them."""

    def test_status_and_lookup_ignore_the_row(self, app, issuer):
        from services.cert.issued_lookup import UNKNOWN, find_issued_rows, issued_certificate_status
        from services.wstep.wstep_service import _renewable_certificate
        ca_id, refid, ca_cert, _ = issuer
        forged, _ = _leaf('forged-row.example.test', ca_cert, _gen())
        _store(app, forged, refid)
        with app.app_context():
            ca = db.session.get(CA, ca_id)
            assert issued_certificate_status(ca, forged) == (None, UNKNOWN)
            assert find_issued_rows(ca, forged) == []  # SCEP renewal and supersession
            row, error = _renewable_certificate(ca, forged)  # WSTEP signed renewal
            assert row is None and error == 'Signing certificate is not recognized'

    def test_a_revoked_forged_row_stays_revoked(self, app, issuer):
        from models import RevokedSerial
        from services.cert.issued_lookup import REVOKED, issued_certificate_status
        ca_id, refid, ca_cert, _ = issuer
        forged, _ = _leaf('forged-revoked.example.test', ca_cert, _gen())
        _store(app, forged, refid)
        with app.app_context():
            db.session.add(RevokedSerial(caref=refid, serial_number=str(forged.serial_number),
                                         valid_to=forged.not_valid_after_utc.replace(tzinfo=None)))
            db.session.commit()
            assert issued_certificate_status(db.session.get(CA, ca_id), forged)[1] == REVOKED

    def test_in_place_renewal_refuses_it(self, app, auth_client, issuer):
        _, refid, ca_cert, _ = issuer
        forged, key = _leaf('forged-renew.example.test', ca_cert, _gen())
        row_id = _store(app, forged, refid, key=key)
        r = auth_client.post(f'/api/v2/certificates/{row_id}/renew', json={})
        assert r.status_code == 400, r.data
        assert 'does not verify with the current key' in r.get_json()['message']
        with app.app_context():
            assert db.session.get(Certificate, row_id).serial_number == str(forged.serial_number)

    def test_a_ca_re_keyed_in_place_asks_for_a_new_certificate(self, app, auth_client, create_ca):
        """Same DN, new key: leaves of the old key no longer renew, and the message says why."""
        data = create_ca(cn=f'Re-keyed CA {uuid.uuid4().hex[:6]}',
                         keyUsage=['digitalSignature', 'keyCertSign', 'cRLSign'])
        with app.app_context():
            from services.hsm.ca_key_loader import get_ca_signing_key
            ca = db.session.get(CA, data['id'])
            old_cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
            leaf, key = _leaf('re-keyed.example.test', old_cert, get_ca_signing_key(ca))
            new_key, now = _gen(), datetime.now(timezone.utc)
            ca.crt = base64.b64encode(_pem(
                x509.CertificateBuilder().subject_name(old_cert.subject).issuer_name(old_cert.subject)
                .public_key(new_key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(new_key.public_key()), critical=False)
                .sign(new_key, hashes.SHA256())).encode()).decode()
            db.session.commit()
            refid = ca.refid
        row_id = _store(app, leaf, refid, key=key)
        r = auth_client.post(f'/api/v2/certificates/{row_id}/renew', json={})
        assert r.status_code == 400, r.data
        message = r.get_json()['message']
        assert 'not signed' not in message
        assert 'does not verify with the current key' in message and 'issue a new certificate' in message

    def test_est_reenrolment_refuses_it(self, app, client, est_config):
        from tests.test_protocol_renewal_identity import _reenrol
        with app.app_context():
            ca = db.session.get(CA, est_config['id'])
            ca_cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
            refid = ca.refid
        forged_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged, _ = _leaf('forged-est.example.test', ca_cert, _gen(), key=forged_key)
        _store(app, forged, refid)
        r = _reenrol(client, forged, forged_key)
        assert r.status_code in (400, 401, 403), r.data


from tests.test_est_rfc7030 import est_config  # noqa: E402,F401  (EST harness)


class TestAnUnverifiableIssuerKeyIsNeverASignature:

    @pytest.fixture
    def unverifiable(self, monkeypatch):
        import utils.cert_issuer as cert_issuer

        def _cannot_tell(cert, issuer_cert):
            raise cert_issuer.UnsupportedIssuerKey('test: key type not checkable')
        monkeypatch.setattr(cert_issuer, 'certificate_signed_by', _cannot_tell)

    def test_a_named_ca_is_refused(self, app, auth_client, issuer, unverifiable):
        ca_id, _, ca_cert, ca_key = issuer
        leaf, _ = _leaf('unverifiable-named.example.test', ca_cert, ca_key)
        r = _import(auth_client, leaf, ca_id=str(ca_id))
        assert r.status_code == 400
        assert 'cannot be verified' in r.get_json()['message']
        assert 'not signed' not in r.get_json()['message']
        assert _rows(app, leaf) == []

    def test_a_named_ca_without_a_certificate_is_refused_as_unverifiable(self, app, auth_client, issuer):
        _, _, ca_cert, ca_key = issuer
        with app.app_context():
            pending = CA(refid=str(uuid.uuid4()), descr='awaiting its certificate', serial=0, crt='',
                         subject=ca_cert.subject.rfc4514_string())
            db.session.add(pending)
            db.session.commit()
            pending_id = pending.id
        leaf, _ = _leaf('unverifiable-pending.example.test', ca_cert, ca_key)
        r = _import(auth_client, leaf, ca_id=str(pending_id))
        assert r.status_code == 400
        assert 'cannot be verified' in r.get_json()['message']
        assert _rows(app, leaf) == []

    def test_a_resolved_ca_is_not_linked(self, app, auth_client, issuer, unverifiable):
        _, _, ca_cert, ca_key = issuer
        leaf, _ = _leaf('unverifiable-auto.example.test', ca_cert, ca_key)
        assert _import(auth_client, leaf).status_code in (200, 201)
        assert [caref for _, caref in _rows(app, leaf)] == [None]


class TestALiveRowNeverHidesAPersistentRevocation:
    """RFC 6960 §2.2: a serial this CA revoked answers ``revoked``, as on its CRL,
    whatever non-revoked row holds that serial now."""

    @staticmethod
    def _answers(app, ca_id, serial):
        from services.crl_service import CRLService
        from services.ocsp_service import OCSPService
        with app.app_context():
            ca = db.session.get(CA, ca_id)
            ocsp = OCSPService._status_for_serial(ca, serial)[1]
            crl = x509.load_pem_x509_crl(CRLService.generate_crl(ca_id).crl_pem.encode())
            return ocsp, crl.get_revoked_certificate_by_serial_number(serial) is not None

    def test_a_forged_row_of_a_revoked_serial(self, app, issuer):
        from models import RevokedSerial
        ca_id, refid, ca_cert, _ = issuer
        forged, _ = _leaf('forged-ocsp.example.test', ca_cert, _gen())
        _store(app, forged, refid)
        with app.app_context():
            db.session.add(RevokedSerial(caref=refid, serial_number=str(forged.serial_number),
                                         valid_to=forged.not_valid_after_utc.replace(tzinfo=None)))
            db.session.commit()
        assert self._answers(app, ca_id, forged.serial_number) == ('revoked', True)

    def test_a_revoked_certificate_deleted_then_imported_again(self, app, auth_client, issuer):
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('revoked-reimported.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid)
        r = auth_client.post(f'/api/v2/certificates/{row_id}/revoke', json={'reason': 'keyCompromise'})
        assert r.status_code == 200, r.data
        assert auth_client.delete(f'/api/v2/certificates/{row_id}').status_code in (200, 204)
        r = _import(auth_client, real, key)
        assert r.status_code in (200, 201), r.data
        [(_, caref)] = _rows(app, real)
        assert caref == refid
        assert self._answers(app, ca_id, real.serial_number) == ('revoked', True)
