"""The EST key generator certificate that signs encrypted serverkeygen packages: made on first
use, reused, replaced near expiry or when the CA certificate changes, one row per CA."""
import base64
import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from asn1crypto import cms
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, padding as asym_padding, rsa
from cryptography.x509.oid import NameOID

from models import CA, Certificate, SystemConfig, db
from models.est_signer_cert import EstSignerCert
from services import est_key_generator
from tests.test_acme_pq import needs_openssl_35
from tests.test_est_rfc7030 import (
    EST_PASSWORD, EST_USER, _basic_auth, _make_csr, _multipart_parts, _post_csr, _set_config,
)
from tests.test_est_serverkeygen_cms import (
    ASYMMETRIC_ID, _decrypt_signed_data, _enrol_transport, _ski, needs_openssl,
    openssl_verify_signed_by,
)
from utils import key_algorithms
from utils.datetime_utils import utc_now

_KEYS = ('est_enabled', 'est_ca_refid', 'est_username', 'est_password', 'est_validity_days')


@pytest.fixture(scope='module')
def cas(create_ca):
    return {'lazy': create_ca(cn='EST generator lazy root'),
            'main': create_ca(cn='EST generator main root')}


@pytest.fixture
def use(app, cas):
    with app.app_context():
        previous = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None)
                    for k in _KEYS}

    def _use(which):
        with app.app_context():
            ca = db.session.get(CA, cas[which]['id'])
            for key, value in (('est_enabled', 'true'), ('est_ca_refid', ca.refid),
                               ('est_username', EST_USER), ('est_password', EST_PASSWORD),
                               ('est_validity_days', '30')):
                _set_config(key, value)
            return ca.id, x509.load_pem_x509_certificate(base64.b64decode(ca.crt))

    yield _use
    with app.app_context():
        for key, value in previous.items():
            row = SystemConfig.query.filter_by(key=key).first()
            if value is None:
                if row is not None:
                    db.session.delete(row)
            elif row is None:
                db.session.add(SystemConfig(key=key, value=value))
            else:
                row.value = value
        db.session.commit()


def _signer_serial(client, cn):
    """Serial of the certificate that signed an encrypted serverkeygen answer."""
    transport, client_key, client_pem = _enrol_transport(client, f'transport-{cn}')
    csr, _ = _make_csr(common_name=cn, extra_attributes=((ASYMMETRIC_ID, _ski(transport)),))
    r = _post_csr(client, 'serverkeygen', csr, client_cert_pem=client_pem)
    assert r.status_code == 200, r.data
    signed = cms.SignedData.load(_decrypt_signed_data(_multipart_parts(r)[1], client_key))
    return signed['signer_infos'][0]['sid'].chosen['serial_number'].native


def _row(app, ca_id):
    with app.app_context():
        return EstSignerCert.query.filter_by(ca_id=ca_id).all()


def _delegate_row(ca_id):
    """The Certificate row the CA's pointer names (inside an app context)."""
    link = EstSignerCert.query.filter_by(ca_id=ca_id).one()
    return db.session.get(Certificate, link.certificate_id)


def _reset(app, ca_id):
    with app.app_context():
        EstSignerCert.query.filter_by(ca_id=ca_id).delete()
        db.session.commit()


class TestLifecycle:

    def test_made_on_the_first_encrypted_request_only(self, app, client, use):
        ca_id, ca_cert = use('lazy')
        assert _row(app, ca_id) == []
        csr, _ = _make_csr(common_name='clear.generator.test')
        assert _post_csr(client, 'serverkeygen', csr, headers=_basic_auth()).status_code == 200
        assert _row(app, ca_id) == []
        serial = _signer_serial(client, 'first.generator.test')
        with app.app_context():
            row = _delegate_row(ca_id)
            delegate = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
            assert int(row.serial_number) == serial == delegate.serial_number
            # The pointer is compared to certificates.serial_number by string equality
            link = EstSignerCert.query.filter_by(ca_id=ca_id).one()
            assert link.serial_number == row.serial_number == str(serial)
            assert row.source == 'est_key_generator' and row.subject_cn == 'EST key generator'
            assert not row.prv.startswith('-----')
            from models import AuditLog
            assert AuditLog.query.filter_by(action='est_key_generator.issued',
                                            resource_id=str(ca_id)).count() == 1
        delegate.verify_directly_issued_by(ca_cert)
        # RFC 5280 §4.2.1.1: the AKI names the CA key
        assert delegate.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value \
            .key_identifier == ca_cert.extensions.get_extension_for_class(
                x509.SubjectKeyIdentifier).value.digest

    def test_reused_across_requests(self, app, client, use):
        ca_id, _ = use('main')
        first = _signer_serial(client, 'reuse-1.generator.test')
        assert _signer_serial(client, 'reuse-2.generator.test') == first
        assert len(_row(app, ca_id)) == 1

    def test_reissued_when_less_than_30_days_remain(self, app, client, use):
        ca_id, _ = use('main')
        first = _signer_serial(client, 'near-1.generator.test')
        with app.app_context():
            row = _delegate_row(ca_id)
            row.valid_to = utc_now() + datetime.timedelta(days=10)
            db.session.commit()
            old_id = row.id
        second = _signer_serial(client, 'near-2.generator.test')
        assert second != first
        with app.app_context():
            assert _delegate_row(ca_id).valid_to - utc_now() > datetime.timedelta(days=300)
            assert db.session.get(Certificate, old_id).archived is True
            from models import AuditLog
            assert AuditLog.query.filter_by(action='est_key_generator.reissued',
                                            resource_id=str(ca_id)).count() >= 1

    def test_reissued_when_the_ca_certificate_changed(self, app, client, use):
        ca_id, _ = use('main')
        first = _signer_serial(client, 'ca-1.generator.test')
        with app.app_context():
            link = EstSignerCert.query.filter_by(ca_id=ca_id).one()
            real = link.issuer_fingerprint
            link.issuer_fingerprint = '0' * 64
            db.session.commit()
        assert _signer_serial(client, 'ca-2.generator.test') != first
        (link,) = _row(app, ca_id)
        assert link.issuer_fingerprint == real

    def test_a_revoked_delegate_is_replaced_and_listed_as_revoked(self, app, client, use):
        from services.crl_service import CRLService
        from services.ocsp_service import OCSPService
        ca_id, _ = use('main')
        first = _signer_serial(client, 'revoked-1.generator.test')
        with app.app_context():
            ca = db.session.get(CA, ca_id)
            assert OCSPService._status_for_serial(ca, first)[1] == 'good'
            row = _delegate_row(ca_id)
            row.revoked, row.revoked_at, row.revoke_reason = True, utc_now(), 'keyCompromise'
            db.session.commit()
            assert OCSPService._status_for_serial(ca, first)[1] == 'revoked'
            crl = x509.load_pem_x509_crl(CRLService.generate_crl(ca_id).crl_pem.encode())
            assert crl.get_revoked_certificate_by_serial_number(first) is not None
        second = _signer_serial(client, 'revoked-2.generator.test')
        assert second != first
        with app.app_context():
            assert OCSPService._status_for_serial(db.session.get(CA, ca_id), second)[1] == 'good'

    def test_an_unreadable_key_is_replaced(self, app, client, use):
        ca_id, _ = use('main')
        first = _signer_serial(client, 'unreadable-1.generator.test')
        with app.app_context():
            row = _delegate_row(ca_id)
            row_id, readable = row.id, row.prv
            row.prv = 'ENC:not-a-fernet-token'
            db.session.commit()
        try:
            assert _signer_serial(client, 'unreadable-2.generator.test') != first
        finally:  # the shared database is backed up by later tests
            with app.app_context():
                db.session.get(Certificate, row_id).prv = readable
                db.session.commit()

    def test_listed_like_a_certificate_and_counted_as_an_issuance(self, app, client, use):
        ca_id, _ = use('main')
        _reset(app, ca_id)
        with app.app_context():
            before = db.session.get(CA, ca_id).serial
        _signer_serial(client, 'uncounted.generator.test')
        with app.app_context():
            # The transport, the delegate and the generated key's certificate each count
            ca = db.session.get(CA, ca_id)
            assert ca.serial == (before or 0) + 3
            assert Certificate.query.filter_by(caref=ca.refid, subject_cn='EST key generator',
                                               archived=False, revoked=False).count() >= 1

    def test_a_failed_issuance_answers_5xx_and_issues_nothing(self, app, client, use):
        ca_id, _ = use('main')
        _reset(app, ca_id)
        transport, _, client_pem = _enrol_transport(client, 'transport-fail.generator.test')
        cn = 'fail.generator.test'
        csr, _ = _make_csr(common_name=cn, extra_attributes=((ASYMMETRIC_ID, _ski(transport)),))
        with patch.object(est_key_generator, '_issue', side_effect=ValueError('CA key unavailable')):
            r = _post_csr(client, 'serverkeygen', csr, client_cert_pem=client_pem)
        assert r.status_code >= 500, r.data
        with app.app_context():
            assert Certificate.query.filter(Certificate.subject_cn == cn).count() == 0
        assert _row(app, ca_id) == []

    def test_two_first_requests_at_once_keep_one_pointer(self, app, use):
        ca_id, ca_cert = use('main')
        original = est_key_generator._issue
        competitor = {}

        def racing_issue(ca, issuer, key):
            # Another worker stores its delegate and pointer between our read and our insert
            other_key = key_algorithms.generate('RSA-3072')
            other_cert, not_after = original(ca, issuer, other_key)
            from sqlalchemy import insert
            row = est_key_generator._certificate_row(ca, other_cert, other_key, not_after)
            with db.engine.begin() as conn:
                values = {c.name: getattr(row, c.name) for c in Certificate.__table__.columns
                          if getattr(row, c.name) is not None}
                cert_id = conn.execute(insert(Certificate.__table__).values(**values)
                                       ).inserted_primary_key[0]
                conn.execute(insert(EstSignerCert.__table__).values(
                    ca_id=ca.id, certificate_id=cert_id, serial_number=row.serial_number,
                    issuer_fingerprint=est_key_generator._fingerprint(issuer), created_at=utc_now()))
            competitor['cert'] = other_cert
            competitor['ours'] = original(ca, issuer, key)
            return competitor['ours']

        _reset(app, ca_id)
        with app.app_context():
            ca = db.session.get(CA, ca_id)
            counted = ca.serial or 0
            with patch.object(est_key_generator, '_issue', side_effect=racing_issue):
                _key, cert = est_key_generator.key_generator(ca, ca_cert)
            assert cert == competitor['cert']
            # The loser's count went with its savepoint too
            assert (db.session.get(CA, ca_id, populate_existing=True).serial or 0) == counted
            assert EstSignerCert.query.filter_by(ca_id=ca_id).count() == 1
            # The loser's certificate row went with its savepoint
            ours = competitor['ours'][0]
            assert Certificate.query.filter_by(serial_number=str(ours.serial_number)).count() == 0
        # The same issuance, unraced this time, counts one
        _reset(app, ca_id)
        with app.app_context():
            est_key_generator.key_generator(db.session.get(CA, ca_id), ca_cert)
            assert (db.session.get(CA, ca_id, populate_existing=True).serial or 0) == counted + 1


def test_a_delegate_renewed_in_place_meanwhile_is_not_archived(app, use, caplog):
    """The replaced delegate is archived only if it still holds the serial read: a row
    renewed in place meanwhile is left live, and this replacement goes with its savepoint."""
    ca_id, ca_cert = use('main')
    with app.app_context():
        est_key_generator.key_generator(db.session.get(CA, ca_id), ca_cert)
        row = _delegate_row(ca_id)
        row.valid_to = utc_now() + datetime.timedelta(days=10)
        db.session.commit()
        old_id, old_serial = row.id, row.serial_number
        counted = db.session.get(CA, ca_id).serial or 0
        db.session.remove()
    original = est_key_generator._certificate_row
    renewed = str(x509.random_serial_number())

    def renewed_in_place_meanwhile(*args):
        from sqlalchemy import update
        with db.engine.begin() as conn:
            conn.execute(update(Certificate.__table__).where(Certificate.__table__.c.id == old_id)
                         .values(serial_number=renewed))
        return original(*args)

    with app.app_context(), caplog.at_level('INFO', logger='services.est_key_generator'):
        with patch.object(est_key_generator, '_certificate_row', side_effect=renewed_in_place_meanwhile):
            with pytest.raises(est_key_generator.DelegateRenewedMeanwhile):
                est_key_generator.key_generator(db.session.get(CA, ca_id), ca_cert)
        assert [r.getMessage() for r in caplog.records if r.name == 'services.est_key_generator'] == [
            f'EST key generator certificate {old_id} of CA {ca_id} was renewed meanwhile; '
            'it is not replaced']
        db.session.rollback()
        db.session.expire_all()
        row = db.session.get(Certificate, old_id)
        link = EstSignerCert.query.filter_by(ca_id=ca_id).one()
        assert (row.serial_number, bool(row.archived)) == (renewed, False)
        assert (link.certificate_id, link.serial_number) == (old_id, old_serial)
        assert (db.session.get(CA, ca_id).serial or 0) == counted
    _reset(app, ca_id)


def test_serverkeygen_answers_409_when_its_delegate_was_renewed_meanwhile(app, client, use):
    ca_id, ca_cert = use('main')
    with app.app_context():
        est_key_generator.key_generator(db.session.get(CA, ca_id), ca_cert)
        row = _delegate_row(ca_id)
        row.valid_to = utc_now() + datetime.timedelta(days=10)
        db.session.commit()
        old_id = row.id
    transport, _, client_pem = _enrol_transport(client, 'transport-renewed.generator.test')
    csr, _ = _make_csr(common_name='renewed.generator.test',
                       extra_attributes=((ASYMMETRIC_ID, _ski(transport)),))
    original = est_key_generator._certificate_row

    def renewed_in_place_meanwhile(*args):
        from sqlalchemy import update
        with db.engine.begin() as conn:
            conn.execute(update(Certificate.__table__).where(Certificate.__table__.c.id == old_id)
                         .values(serial_number=str(x509.random_serial_number())))
        return original(*args)

    with patch.object(est_key_generator, '_certificate_row', side_effect=renewed_in_place_meanwhile):
        r = _post_csr(client, 'serverkeygen', csr, client_cert_pem=client_pem)
    assert r.status_code == 409, r.data
    assert b'renewed meanwhile' in r.data
    with app.app_context():
        assert Certificate.query.filter_by(subject_cn='renewed.generator.test').count() == 0
    _reset(app, ca_id)


def _ca_like(key, *, hsm_key_id=None, name=None, days=3650, extensions=()):
    from utils.key_codec import store_pem_bytes
    name = name or x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Generator Org'),
                              x509.NameAttribute(NameOID.COMMON_NAME, 'Generator test CA')])
    now = datetime.datetime.now(datetime.timezone.utc)
    digest = hashes.SHA256() if key_algorithms.needs_digest(key) else None
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=days))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False),
                           critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False))
    for extension in extensions:
        cert = cert.add_extension(extension, critical=True)
    cert = cert.sign(key, digest)
    prv = None if hsm_key_id else store_pem_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    ca = SimpleNamespace(id=0, refid='generator-test', descr='Generator test CA', offline=False,
                         offline_reason=None, is_pending=False, hsm_key_id=hsm_key_id, prv=prv,
                         signature_scheme=None, revoked_in_chain=False)
    return ca, cert


def _ca_keys():
    keys = {
        'RSA-2048': (lambda: rsa.generate_private_key(65537, 2048), 'RSA-3072'),
        'EC-P384': (lambda: ec.generate_private_key(ec.SECP384R1()), 'EC-P384'),
        'EC-BP256': (lambda: ec.generate_private_key(ec.BrainpoolP256R1()), 'EC-BP256'),
        'ED25519': (ed25519.Ed25519PrivateKey.generate, 'ED25519'),
        'ED448': (ed448.Ed448PrivateKey.generate, 'ED25519'),
    }
    if key_algorithms.mldsa_supported():
        keys['ML-DSA-65'] = (lambda: key_algorithms.generate('ML-DSA-65'), 'ML-DSA-65')
    return keys


@needs_openssl
@pytest.mark.parametrize('ca_label', [
    pytest.param(name, marks=needs_openssl_35) if name.startswith('ML-DSA') else name
    for name in sorted(_ca_keys())])
def test_each_ca_family_issues_a_delegate_openssl_chains_to_the_ca(app, ca_label, tmp_path):
    from utils.est_cms import signed_key_package
    make, expected_label = _ca_keys()[ca_label]
    ca, ca_cert = _ca_like(make())
    with app.app_context():
        label = est_key_generator.delegate_key_label(ca_cert.public_key())
        assert label == expected_label
        delegate_key = key_algorithms.generate(label)
        delegate, _ = est_key_generator._issue(ca, ca_cert, delegate_key)
    usage = delegate.extensions.get_extension_for_class(x509.KeyUsage)
    assert usage.critical and usage.value.digital_signature and not usage.value.key_cert_sign
    signed = signed_key_package(ec.generate_private_key(ec.SECP256R1()), delegate_key, delegate,
                                (ca_cert,))
    (tmp_path / 'signed.p7').write_bytes(
        cms.ContentInfo({'content_type': 'signed_data', 'content': signed}).dump())
    (tmp_path / 'anchor.pem').write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    openssl_verify_signed_by(tmp_path / 'signed.p7', tmp_path / 'anchor.pem', delegate, tmp_path)


@pytest.mark.parametrize('ca_label, expected', [
    ('RSA-2048', 'RSA-3072'), ('EC-P384', 'EC-P384'), ('EC-BP256', 'EC-P256'),
    ('ED25519', 'EC-P256'), ('ED448', 'EC-P384'), ('ML-DSA-65', 'EC-P384')])
def test_fips_mode_keeps_the_delegate_on_approved_keys(monkeypatch, ca_label, expected):
    import fips_mode
    if ca_label not in _ca_keys():
        pytest.skip('this build has no ML-DSA')
    key = _ca_keys()[ca_label][0]()
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    assert est_key_generator.delegate_key_label(key.public_key()) == expected


def test_an_hsm_backed_ca_signs_the_delegate_through_its_provider(app):
    from services.hsm.hsm_private_key import HsmRSAPrivateKey
    real = rsa.generate_private_key(65537, 2048)
    ca, ca_cert = _ca_like(real, hsm_key_id=77)
    calls = []

    def provider_sign(key_id, data, algorithm=None, hash_algorithm=None, padding=None):
        calls.append((key_id, hash_algorithm))
        return real.sign(data, asym_padding.PKCS1v15(), getattr(hashes, hash_algorithm.upper())())

    with app.app_context(), \
            patch('services.hsm.ca_key_loader.load_hsm_private_key',
                  return_value=HsmRSAPrivateKey(77, real.public_key(), 'RSA-2048')), \
            patch('services.hsm.HsmService.signing_hash', side_effect=lambda k, a, r='sha256': r), \
            patch('services.hsm.HsmService.sign', side_effect=provider_sign):
        delegate, _ = est_key_generator._issue(ca, ca_cert, key_algorithms.generate('RSA-3072'))
    assert calls and calls[0][0] == 77
    delegate.verify_directly_issued_by(ca_cert)


def test_an_offline_ca_issues_no_delegate(app):
    ca, ca_cert = _ca_like(rsa.generate_private_key(65537, 2048))
    ca.offline = True
    from services.ca.ca_signing import CAOfflineError
    with app.app_context(), pytest.raises(CAOfflineError):
        est_key_generator._issue(ca, ca_cert, key_algorithms.generate('RSA-3072'))


def test_the_delegate_is_revoked_and_deleted_like_any_certificate_before_its_ca(
        app, auth_client, create_ca):
    ca_data = create_ca(cn='EST generator deleted root')
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        est_key_generator.key_generator(ca, x509.load_pem_x509_certificate(base64.b64decode(ca.crt)))
        row_id = _delegate_row(ca.id).id
    # Like a delegated OCSP responder: the issued certificate holds the CA back until removed
    assert auth_client.delete(f"/api/v2/cas/{ca_data['id']}").status_code == 409
    with app.app_context():
        row = db.session.get(Certificate, row_id)
        row.revoked, row.revoked_at = True, utc_now()
        db.session.delete(row)
        db.session.commit()
    assert auth_client.delete(f"/api/v2/cas/{ca_data['id']}").status_code in (200, 204)
    with app.app_context():
        assert EstSignerCert.query.filter_by(ca_id=ca_data['id']).count() == 0


def test_the_subject_keeps_every_ca_rdn_so_dirname_constraints_hold(app, tmp_path):
    """A CA C=FR, O=Generator Org with permitted dirName C=FR, O=Generator Org (RFC 5280 §4.2.1.10)."""
    from tests.test_acme_pq import OPENSSL
    if not OPENSSL:
        pytest.skip('needs the openssl command')
    base = x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, 'FR'),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Generator Org')])
    ca, ca_cert = _ca_like(
        rsa.generate_private_key(65537, 2048), name=base,
        extensions=(x509.NameConstraints(permitted_subtrees=[x509.DirectoryName(base)],
                                         excluded_subtrees=None),))
    with app.app_context():
        delegate, _ = est_key_generator._issue(ca, ca_cert, key_algorithms.generate('RSA-3072'))
    assert delegate.subject == x509.Name([*base, x509.NameAttribute(NameOID.COMMON_NAME,
                                                                     'EST key generator')])
    (tmp_path / 'ca.pem').write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    (tmp_path / 'delegate.pem').write_bytes(delegate.public_bytes(serialization.Encoding.PEM))
    import subprocess
    verify = subprocess.run([OPENSSL, 'verify', '-CAfile', str(tmp_path / 'ca.pem'),
                             str(tmp_path / 'delegate.pem')], capture_output=True, text=True)
    assert verify.returncode == 0, verify.stdout + verify.stderr


def test_under_a_ca_expiring_soon_the_delegate_never_outlives_it(app):
    ca, ca_cert = _ca_like(rsa.generate_private_key(65537, 2048), days=45)
    with app.app_context():
        delegate, _ = est_key_generator._issue(ca, ca_cert, key_algorithms.generate('RSA-3072'))
    assert delegate.not_valid_after_utc <= ca_cert.not_valid_after_utc
    assert delegate.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value \
        .key_identifier == ca_cert.extensions.get_extension_for_class(
            x509.SubjectKeyIdentifier).value.digest


def _serial_of(row):
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt)).serial_number


class TestPointerIdentity:
    """SQLite runs no ON DELETE CASCADE and reuses a deleted certificate's id."""

    def test_a_pointer_to_a_reused_id_never_signs_with_that_certificate(
            self, app, client, use, cas, create_cert):
        ca_id, _ = use('main')
        _signer_serial(client, 'reuse-id-1.generator.test')
        victim = create_cert(cn='victim.generator.test', ca_id=ca_id)
        with app.app_context():
            victim_serial = _serial_of(db.session.get(Certificate, victim['id']))
            link = EstSignerCert.query.filter_by(ca_id=ca_id).one()
            link.certificate_id = victim['id']  # what id reuse does to a dangling pointer
            db.session.commit()
        signer = _signer_serial(client, 'reuse-id-2.generator.test')
        assert signer != victim_serial
        with app.app_context():
            assert db.session.get(Certificate, victim['id']).archived is not True
            assert int(_delegate_row(ca_id).serial_number) == signer

    def test_deleting_the_delegate_through_the_api_drops_its_pointer(
            self, app, client, auth_client, use, create_cert):
        ca_id, _ = use('main')
        first = _signer_serial(client, 'deleted-1.generator.test')
        with app.app_context():
            row_id = _delegate_row(ca_id).id
        assert auth_client.post(f'/api/v2/certificates/{row_id}/revoke', json={'reason': 'superseded'}
                                ).status_code == 200
        assert auth_client.delete(f'/api/v2/certificates/{row_id}').status_code in (200, 204)
        assert _row(app, ca_id) == []
        victim = create_cert(cn='after-delete.generator.test', ca_id=ca_id)
        signer = _signer_serial(client, 'deleted-2.generator.test')
        with app.app_context():
            assert signer not in (first, _serial_of(db.session.get(Certificate, victim['id'])))
            assert int(_delegate_row(ca_id).serial_number) == signer


def test_no_expiry_alert_for_a_key_generator(app, use, client):
    import json
    from models.email_notification import NotificationConfig
    from services.expiry_alert_service import get_expiring_certificates
    from services.notification.scheduler import NotificationSchedulerMixin
    ca_id, _ = use('main')
    _signer_serial(client, 'alert.generator.test')
    with app.app_context():
        row = _delegate_row(ca_id)
        row.valid_to = utc_now() + datetime.timedelta(hours=12)
        db.session.commit()
        row_id = row.id
        assert row_id not in [c['id'] for c in get_expiring_certificates(days=30)]
        config = NotificationConfig.query.filter_by(type='cert_expiring').first()
        previous = None
        if not config:
            config = NotificationConfig(type='cert_expiring')
            db.session.add(config)
        else:
            previous = (config.enabled, config.get_alert_days(), config.recipients)
        config.enabled = True
        config.set_alert_days([1, 7, 30])
        config.include_revoked = False
        config.recipients = json.dumps(['ops@example.test'])
        db.session.commit()
        try:
            due = NotificationSchedulerMixin.check_expiring_certificates()
            assert row_id not in [entry['cert'].id for entry in due]
        finally:
            if previous is None:
                db.session.delete(config)
            else:
                config.enabled, days, config.recipients = previous
                config.set_alert_days(days)
            row.valid_to = utc_now() + datetime.timedelta(days=365)
            db.session.commit()
