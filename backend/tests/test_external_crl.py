"""
Tests for externally-signed CRL upload on key-less / offline CAs (#302):
validation (issuer, signature, profile), monotonicity, CDP serving and the
OCSP lookup path.
"""
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from tests.conftest import assert_error, assert_success, get_json

BASE = '/api/v2/cas'

_seq = [0]


def _next_name(prefix='ExtCRL Root'):
    _seq[0] += 1
    return f'{prefix} {_seq[0]}'


def _make_offline_root(cn=None):
    """Self-signed root built with cryptography only — simulates the offline CA."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048,
                                   backend=default_backend())
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, cn or _next_name()),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Offline Org'),
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=False, content_commitment=False,
            key_encipherment=False, data_encipherment=False, key_agreement=False,
            key_cert_sign=True, crl_sign=True, encipher_only=False,
            decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                       critical=False)
        .sign(key, hashes.SHA256(), default_backend())
    )
    return key, cert


def _build_crl(root_key, root_cert, *, entries=(), number=1, days_valid=7,
               this_update=None, with_number=True,
               delta_base=None, issuer=None, encoding='pem'):
    """Reproduce what an admin does next to the offline root key."""
    now = this_update or datetime.now(timezone.utc)
    builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(issuer or root_cert.subject)
        .last_update(now)
        .next_update(now + timedelta(days=days_valid))
    )
    for serial, revoked_at, reason in entries:
        rb = (
            x509.RevokedCertificateBuilder()
            .serial_number(serial)
            .revocation_date(revoked_at)
        )
        if reason is not None:
            rb = rb.add_extension(x509.CRLReason(reason), critical=False)
        builder = builder.add_revoked_certificate(rb.build())
    if with_number:
        builder = builder.add_extension(x509.CRLNumber(number), critical=False)
    if delta_base is not None:
        builder = builder.add_extension(
            x509.DeltaCRLIndicator(delta_base), critical=True)
    crl = builder.sign(root_key, hashes.SHA256(), default_backend())
    if encoding == 'der':
        return crl.public_bytes(serialization.Encoding.DER)
    return crl.public_bytes(serialization.Encoding.PEM)


def _import_root_cert_only(auth_client, root_cert, name=None):
    """Certificate-only import — the canonical key-less CA."""
    pem = root_cert.public_bytes(serialization.Encoding.PEM).decode()
    r = auth_client.post(f'{BASE}/import', data={
        'pem_content': pem, 'name': name or _next_name('Import'), 'import_key': 'false',
    })
    assert r.status_code in (200, 201), r.data[:400]
    return get_json(r).get('data', {})


def _upload_pem(auth_client, ca_id, crl_pem):
    return auth_client.post(
        f'{BASE}/{ca_id}/crl',
        data=json.dumps({'pem_content': crl_pem.decode()}),
        content_type='application/json',
    )


@pytest.fixture()
def keyless_ca(auth_client):
    """(root_key, root_cert, imported CA dict) for a certificate-only import."""
    root_key, root_cert = _make_offline_root()
    ca = _import_root_cert_only(auth_client, root_cert)
    assert ca.get('has_private_key') is False
    return root_key, root_cert, ca


class TestUploadValidation:
    def test_upload_valid_pem(self, auth_client, keyless_ca):
        root_key, root_cert, ca = keyless_ca
        now = datetime.now(timezone.utc)
        crl_pem = _build_crl(root_key, root_cert, entries=(
            (0x1001, now - timedelta(hours=1), x509.ReasonFlags.superseded),
        ))
        data = assert_success(_upload_pem(auth_client, ca['id'], crl_pem))
        assert data['is_external'] is True
        assert data['crl_number'] == 1
        assert data['revoked_count'] == 1
        assert data['is_stale'] is False

    def test_upload_der_file(self, auth_client, keyless_ca):
        root_key, root_cert, ca = keyless_ca
        crl_der = _build_crl(root_key, root_cert, encoding='der')
        r = auth_client.post(
            f"{BASE}/{ca['id']}/crl",
            data={'file': (io.BytesIO(crl_der), 'root.crl')},
            content_type='multipart/form-data',
        )
        data = assert_success(r)
        assert data['is_external'] is True

    def test_reject_ca_with_private_key(self, auth_client, create_ca):
        ca = create_ca()
        root_key, root_cert = _make_offline_root()
        crl_pem = _build_crl(root_key, root_cert)
        assert_error(_upload_pem(auth_client, ca['id'], crl_pem), 409)

    def test_reject_wrong_signature(self, auth_client, keyless_ca):
        _, root_cert, ca = keyless_ca
        other_key, _ = _make_offline_root('Impostor Root')
        forged = _build_crl(other_key, root_cert)  # right DN, wrong key
        r = _upload_pem(auth_client, ca['id'], forged)
        assert_error(r, 400)
        assert 'signature' in get_json(r)['message'].lower()

    def test_reject_issuer_mismatch(self, auth_client, keyless_ca):
        root_key, root_cert, ca = keyless_ca
        other = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Someone Else')])
        crl_pem = _build_crl(root_key, root_cert, issuer=other)
        r = _upload_pem(auth_client, ca['id'], crl_pem)
        assert_error(r, 400)
        assert 'issuer' in get_json(r)['message'].lower()

    def test_reject_delta_crl(self, auth_client, keyless_ca):
        root_key, root_cert, ca = keyless_ca
        crl_pem = _build_crl(root_key, root_cert, number=2, delta_base=1)
        r = _upload_pem(auth_client, ca['id'], crl_pem)
        assert_error(r, 400)
        assert 'delta' in get_json(r)['message'].lower()

    def test_reject_garbage(self, auth_client, keyless_ca):
        _, _, ca = keyless_ca
        assert_error(_upload_pem(auth_client, ca['id'], b'not a crl'), 400)

    def test_reject_unknown_ca(self, auth_client):
        root_key, root_cert = _make_offline_root()
        crl_pem = _build_crl(root_key, root_cert)
        assert_error(_upload_pem(auth_client, 999999, crl_pem), 404)

    def test_requires_auth(self, client, keyless_ca):
        _, _, ca = keyless_ca
        r = client.post(f"{BASE}/{ca['id']}/crl", data=json.dumps({'pem_content': 'x'}),
                        content_type='application/json')
        assert r.status_code in (401, 403)

    def test_stale_crl_accepted_and_flagged(self, auth_client, keyless_ca):
        # Better stale than nothing (RFC 5280 §6.3.3) — accepted, flagged stale.
        root_key, root_cert, ca = keyless_ca
        crl_pem = _build_crl(
            root_key, root_cert,
            this_update=datetime.now(timezone.utc) - timedelta(days=30),
            days_valid=7,
        )
        data = assert_success(_upload_pem(auth_client, ca['id'], crl_pem))
        assert data['is_stale'] is True


class TestMonotonicity:
    def test_newer_replaces_older(self, auth_client, keyless_ca):
        root_key, root_cert, ca = keyless_ca
        now = datetime.now(timezone.utc)
        assert_success(_upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert, number=1, this_update=now - timedelta(hours=2))))
        data = assert_success(_upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert, number=2, this_update=now)))
        assert data['crl_number'] == 2

    def test_reject_crl_number_regression(self, auth_client, keyless_ca):
        root_key, root_cert, ca = keyless_ca
        now = datetime.now(timezone.utc)
        assert_success(_upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert, number=5, this_update=now - timedelta(hours=2))))
        r = _upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert, number=4, this_update=now))
        assert_error(r, 409)
        assert 'number' in get_json(r)['message'].lower()

    def test_reject_older_this_update(self, auth_client, keyless_ca):
        root_key, root_cert, ca = keyless_ca
        now = datetime.now(timezone.utc)
        assert_success(_upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert, number=1, this_update=now)))
        assert_error(_upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert, number=2, this_update=now - timedelta(days=1))), 409)

    def test_reject_exact_duplicate(self, auth_client, keyless_ca):
        root_key, root_cert, ca = keyless_ca
        this_update = datetime.now(timezone.utc).replace(microsecond=0)
        crl_pem = _build_crl(root_key, root_cert, number=1, this_update=this_update)
        assert_success(_upload_pem(auth_client, ca['id'], crl_pem))
        assert_error(_upload_pem(auth_client, ca['id'], crl_pem), 409)

    def test_reject_a_second_crl_under_the_same_number(self, auth_client, keyless_ca):
        # RFC 5280 §5.2.3: two CRLs with different thisUpdate MUST have different numbers
        root_key, root_cert, ca = keyless_ca
        now = datetime.now(timezone.utc)
        assert_success(_upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert, number=3, this_update=now - timedelta(hours=1))))
        r = _upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert, number=3, this_update=now))
        assert_error(r, 409)
        assert 'number 3' in get_json(r)['message']

    def test_no_crl_number_extension(self, auth_client, keyless_ca):
        # openssl `ca -gencrl` omits CRLNumber unless configured — the internal
        # counter keeps ordering monotonic.
        root_key, root_cert, ca = keyless_ca
        now = datetime.now(timezone.utc)
        d1 = assert_success(_upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert, with_number=False, this_update=now - timedelta(hours=1))))
        assert d1['crl_number'] == 1
        d2 = assert_success(_upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert, with_number=False, this_update=now)))
        assert d2['crl_number'] == 2


class TestServingAndOCSP:
    def test_served_on_cdp_path(self, auth_client, client, keyless_ca):
        root_key, root_cert, ca = keyless_ca
        crl_der = _build_crl(root_key, root_cert, encoding='der')
        crl_pem = _build_crl(root_key, root_cert)
        assert_success(_upload_pem(auth_client, ca['id'], crl_pem))
        r = client.get(f"/cdp/{ca['refid']}.crl")
        assert r.status_code == 200
        assert r.mimetype == 'application/pkix-crl'
        served = x509.load_der_x509_crl(r.data, default_backend())
        assert served.issuer == root_cert.subject

    def test_crl_api_reports_external(self, auth_client, keyless_ca):
        root_key, root_cert, ca = keyless_ca
        assert_success(_upload_pem(auth_client, ca['id'], _build_crl(root_key, root_cert)))
        data = assert_success(auth_client.get(f"/api/v2/crl/{ca['id']}"))
        assert data['is_external'] is True

    def test_ocsp_status_uses_external_crl(self, app, auth_client, keyless_ca):
        root_key, root_cert, ca = keyless_ca
        now = datetime.now(timezone.utc)
        revoked_serial = 0xABCDEF
        crl_pem = _build_crl(root_key, root_cert, entries=(
            (revoked_serial, now - timedelta(hours=3), x509.ReasonFlags.key_compromise),
        ))
        assert_success(_upload_pem(auth_client, ca['id'], crl_pem))

        from models import db, CA
        from services.ocsp_service import OCSPService
        with app.app_context():
            ca_obj = db.session.get(CA, ca['id'])
            _, status, revoked_at, reason = OCSPService._status_for_serial(
                ca_obj, revoked_serial)
            assert status == 'revoked'
            assert reason == x509.ReasonFlags.key_compromise
            assert revoked_at is not None

            _, status, _, _ = OCSPService._status_for_serial(ca_obj, 0x1234)
            assert status == 'unknown'

    def test_external_revocation_cache_invalidated_on_upload(
            self, app, auth_client, keyless_ca):
        root_key, root_cert, ca = keyless_ca
        now = datetime.now(timezone.utc)
        s1, s2 = 0x111, 0x222
        assert_success(_upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert, number=1, this_update=now - timedelta(hours=1),
            entries=((s1, now - timedelta(hours=2), None),))))

        from services.crl_service import CRLService
        with app.app_context():
            assert CRLService.get_external_revocation(ca['id'], s1) is not None
            assert CRLService.get_external_revocation(ca['id'], s2) is None

        assert_success(_upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert, number=2, this_update=now,
            entries=((s1, now - timedelta(hours=2), None),
                     (s2, now - timedelta(hours=1), None)))))
        with app.app_context():
            revoked_at, reason = CRLService.get_external_revocation(ca['id'], s2)
            assert reason is None  # no CRLReason on the entry — stays None

    def test_single_certid_ocsp_path_uses_external_crl(
            self, app, auth_client, keyless_ca, monkeypatch):
        """generate_response (the single-CertID path) must consult the external
        CRL like _status_for_serial does — review F-01. Without a signing key
        or responder the response is 'unauthorized', but the resolved status
        must be computed from the CRL, so we give the CA a delegated responder."""
        from cryptography.hazmat.primitives.asymmetric import rsa as _rsa
        from cryptography.x509 import ocsp as x509_ocsp
        root_key, root_cert, ca = keyless_ca
        now = datetime.now(timezone.utc)
        revoked_serial = 0xF01F01
        assert_success(_upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert,
            entries=((revoked_serial, now - timedelta(hours=1),
                      x509.ReasonFlags.superseded),))))

        from models import db, CA, Certificate, SystemConfig
        from services.ocsp_service import OCSPService
        from datetime import timedelta as _td
        with app.app_context():
            ca_obj = db.session.get(CA, ca['id'])
            # Delegated responder issued next to the offline root key
            responder_key = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
            responder_cert = (
                x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Ext Responder')]))
                .issuer_name(root_cert.subject)
                .public_key(responder_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - _td(minutes=5))
                .not_valid_after(now + _td(days=30))
                .add_extension(x509.ExtendedKeyUsage(
                    [x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING]), critical=False)
                .add_extension(x509.OCSPNoCheck(), critical=False)
                .sign(root_key, hashes.SHA256())
            )
            import base64 as _b64
            record = Certificate(
                refid=f'ext-resp-{ca["id"]}', descr='ext responder',
                caref=ca_obj.refid,
                crt=_b64.b64encode(responder_cert.public_bytes(
                    serialization.Encoding.PEM)).decode(),
                prv=_b64.b64encode(responder_key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption())).decode(),
            )
            db.session.add(record)
            db.session.flush()
            db.session.add(SystemConfig(
                key=f'ocsp_responder_cert_{ca_obj.id}', value=str(record.id)))
            db.session.commit()
            monkeypatch.setattr(
                'security.encryption.decrypt_private_key', lambda value: value)

            der, status = OCSPService().generate_response(ca_obj, revoked_serial)
            assert status == 'revoked'
            resp = x509_ocsp.load_der_ocsp_response(der)
            assert resp.response_status == x509_ocsp.OCSPResponseStatus.SUCCESSFUL
            assert resp.certificate_status == x509_ocsp.OCSPCertStatus.REVOKED

            der, status = OCSPService().generate_response(ca_obj, 0x123456)
            assert status == 'unknown'

    def test_upload_purges_cached_ocsp_responses(self, app, auth_client, keyless_ca):
        """A pre-generated 'good' OCSP answer must not survive a CRL upload
        that revokes the serial — review F-03."""
        root_key, root_cert, ca = keyless_ca
        serial = 0xF03F03
        from models import db, OCSPResponse
        from utils.datetime_utils import utc_now
        from datetime import timedelta as _td
        with app.app_context():
            db.session.add(OCSPResponse(
                ca_id=ca['id'], cert_serial=f'{serial:x}:sha256',
                response_der=b'cached', status='good',
                this_update=utc_now(), next_update=utc_now() + _td(hours=24)))
            db.session.commit()

        now = datetime.now(timezone.utc)
        assert_success(_upload_pem(auth_client, ca['id'], _build_crl(
            root_key, root_cert,
            entries=((serial, now - timedelta(hours=1), None),))))

        with app.app_context():
            assert OCSPResponse.query.filter_by(ca_id=ca['id']).count() == 0

    def test_no_external_lookup_for_internal_crl(self, app, auth_client, create_ca):
        ca = create_ca()
        assert_success(auth_client.post(f"/api/v2/crl/{ca['id']}/regenerate"))
        from services.crl_service import CRLService
        with app.app_context():
            assert CRLService.get_external_revocation(ca['id'], 0x1) is None


class TestOfflineFileExportedCA:
    def test_upload_after_take_offline(self, auth_client, create_ca):
        """A UCM-born CA taken offline (file-exported key) accepts external CRLs,
        and the CRL number must continue past the internally generated ones."""
        ca = create_ca()
        assert_success(auth_client.post(f"/api/v2/crl/{ca['id']}/regenerate"))

        r = auth_client.post(f"{BASE}/{ca['id']}/offline", data=json.dumps({
            'password': 'OfflineTest123!', 'mode': 'file_exported',
        }), content_type='application/json')
        assert r.status_code == 200, r.data[:400]

        # Rebuild the root key/cert pair externally is impossible here (the key
        # left as an encrypted file), so simulate with a fresh root whose DN and
        # key do NOT match — the upload must fail on signature, proving the
        # eligibility gate itself passed (409 would mean 'CA can sign').
        other_key, other_cert = _make_offline_root('Not The Same Root')
        r = _upload_pem(auth_client, ca['id'], _build_crl(other_key, other_cert))
        assert r.status_code == 400
        assert 'issuer' in get_json(r)['message'].lower()
