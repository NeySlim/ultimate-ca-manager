"""
RFC 5280 CRL profile follow-up — non-regression, bug, security, lab checks.

Covers gaps beyond #202 (AKI):
  §5.2.4  base+delta IDP must both omit or be identical (UCM omits both)
  §5.2.6  FreshestCRL only when CDP present; never raises on missing CDP
  §5.3.1  omit unspecified; removeFromCRL delta-only
  §5.2.1  AKI still == signing CA SKI (smoke)
  Auth     regenerate endpoints require authentication
"""
import base64
import json
import os
import sys
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import CRLEntryExtensionOID, ExtensionOID

from tests.conftest import assert_success, get_json
from utils.datetime_utils import utc_now

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTENT_JSON = 'application/json'
CRL_BASE = '/api/v2/crl'


def _post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


def _ext_or_none(obj, oid):
    try:
        return obj.extensions.get_extension_for_oid(oid)
    except x509.ExtensionNotFound:
        return None


def _load_crl(pem: str):
    return x509.load_pem_x509_crl(
        pem.encode() if isinstance(pem, str) else pem,
        default_backend(),
    )


def _fetch_crl_pem(auth_client, ca_id, *, delta=False):
    url = f'{CRL_BASE}/{ca_id}/delta' if delta else f'{CRL_BASE}/{ca_id}'
    r = auth_client.get(url)
    assert r.status_code == 200, r.data
    data = get_json(r).get('data', get_json(r))
    assert data and data.get('crl_pem'), data
    return data['crl_pem']


def _enable_delta(app, ca_id):
    with app.app_context():
        from models import CA, db
        ca = db.session.get(CA, ca_id)
        ca.cdp_enabled = True
        ca.delta_crl_enabled = True
        ca.set_cdp_urls([f'http://cdp.test.local/cdp/{ca.refid}.crl'])
        db.session.commit()
        return ca.refid


def _make_intermediate(auth_client, create_ca, cn_root, cn_int):
    root = create_ca(cn=cn_root)
    r = _post_json(auth_client, '/api/v2/cas', {
        'type': 'intermediate',
        'commonName': cn_int,
        'organization': 'Test Org',
        'country': 'US',
        'state': 'CA',
        'locality': 'Test City',
        'keyType': 'RSA',
        'keySize': 2048,
        'validityYears': 5,
        'hashAlgorithm': 'sha256',
        'parentCAId': root['id'],
    })
    return root, assert_success(r, status=201)


def _issue_and_revoke(auth_client, ca_id, cn, reason):
    r = _post_json(auth_client, '/api/v2/certificates', {
        'cn': cn,
        'ca_id': ca_id,
        'validity_days': 30,
    })
    cert = assert_success(r, status=201)
    r = _post_json(auth_client, f'/api/v2/certificates/{cert["id"]}/revoke', {
        'reason': reason,
    })
    assert r.status_code in (200, 201), r.data
    return cert


class TestRfc5280IdpParity:
    """§5.2.4 — base and delta must both omit IDP or carry identical IDP."""

    def test_full_and_delta_both_omit_idp(self, app, auth_client, create_ca):
        ca = create_ca(cn='IDP Parity CA')
        _enable_delta(app, ca['id'])

        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/regenerate').status_code == 200
        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/delta/regenerate').status_code == 200

        full = _load_crl(_fetch_crl_pem(auth_client, ca['id']))
        delta = _load_crl(_fetch_crl_pem(auth_client, ca['id'], delta=True))

        assert _ext_or_none(full, ExtensionOID.ISSUING_DISTRIBUTION_POINT) is None
        assert _ext_or_none(delta, ExtensionOID.ISSUING_DISTRIBUTION_POINT) is None
        assert _ext_or_none(delta, ExtensionOID.DELTA_CRL_INDICATOR) is not None


class TestRfc5280FreshestCrl:
    """§5.2.6 — FreshestCRL on complete CRL when delta+CDP configured."""

    def test_freshest_crl_present_when_delta_and_cdp(self, app, auth_client, create_ca):
        ca = create_ca(cn='Freshest CDP CA')
        refid = _enable_delta(app, ca['id'])
        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/regenerate').status_code == 200

        full = _load_crl(_fetch_crl_pem(auth_client, ca['id']))
        freshest = _ext_or_none(full, ExtensionOID.FRESHEST_CRL)
        assert freshest is not None
        assert freshest.critical is False
        uris = [
            n.value
            for dp in freshest.value
            for n in (dp.full_name or [])
        ]
        assert any(refid in u and 'delta' in u for u in uris)

    def test_freshest_crl_absent_without_cdp_no_crash(self, app, auth_client, create_ca):
        """Bug: old code referenced delta_url outside the CDP guard."""
        ca = create_ca(cn='Freshest NoCDP CA')
        with app.app_context():
            from models import CA, db
            row = db.session.get(CA, ca['id'])
            row.delta_crl_enabled = True
            row.cdp_enabled = False
            row.cdp_url = None
            db.session.commit()

        r = auth_client.post(f'{CRL_BASE}/{ca["id"]}/regenerate')
        assert r.status_code == 200, r.data
        full = _load_crl(_fetch_crl_pem(auth_client, ca['id']))
        assert _ext_or_none(full, ExtensionOID.FRESHEST_CRL) is None

    def test_delta_must_not_carry_freshest_crl(self, app, auth_client, create_ca):
        ca = create_ca(cn='Freshest Delta CA')
        _enable_delta(app, ca['id'])
        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/regenerate').status_code == 200
        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/delta/regenerate').status_code == 200
        delta = _load_crl(_fetch_crl_pem(auth_client, ca['id'], delta=True))
        assert _ext_or_none(delta, ExtensionOID.FRESHEST_CRL) is None


class TestRfc5280ReasonCode:
    """§5.3.1 — omit unspecified; removeFromCRL only on delta."""

    def test_unspecified_reason_omitted_from_full_crl(self, app, auth_client, create_ca):
        ca = create_ca(cn='Reason Unspec CA')
        cert = _issue_and_revoke(
            auth_client, ca['id'], 'unspec.reason.test', 'unspecified')
        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/regenerate').status_code == 200

        crl = _load_crl(_fetch_crl_pem(auth_client, ca['id']))
        assert len(list(crl)) >= 1
        for entry in crl:
            assert _ext_or_none(entry, CRLEntryExtensionOID.CRL_REASON) is None

    def test_meaningful_reason_present(self, app, auth_client, create_ca):
        ca = create_ca(cn='Reason KeyComp CA')
        _issue_and_revoke(auth_client, ca['id'], 'keycomp.reason.test', 'keyCompromise')
        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/regenerate').status_code == 200
        crl = _load_crl(_fetch_crl_pem(auth_client, ca['id']))
        reasons = []
        for entry in crl:
            ext = _ext_or_none(entry, CRLEntryExtensionOID.CRL_REASON)
            if ext:
                reasons.append(ext.value.reason)
        assert x509.ReasonFlags.key_compromise in reasons

    def test_remove_from_crl_omitted_on_full_included_on_delta(
            self, app, auth_client, create_ca):
        ca = create_ca(cn='Reason Remove CA')
        _enable_delta(app, ca['id'])

        # Seed a base CRL first, then plant a removeFromCRL row after thisUpdate.
        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/regenerate').status_code == 200

        with app.app_context():
            from models import CA, Certificate, db
            from services.cert_service import CertificateService
            ca_row = db.session.get(CA, ca['id'])
            # Issue via API path already used above; create+flag directly for reason control
            r = _post_json(auth_client, '/api/v2/certificates', {
                'cn': 'remove.reason.test',
                'ca_id': ca['id'],
                'validity_days': 30,
            })
            cert = assert_success(r, status=201)
            row = db.session.get(Certificate, cert['id'])
            row.revoked = True
            row.revoke_reason = 'removeFromCRL'
            row.revoked_at = utc_now() + timedelta(seconds=2)
            db.session.commit()
            caref = ca_row.refid

        # Full CRL must list the cert without removeFromCRL reason extension
        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/regenerate').status_code == 200
        full = _load_crl(_fetch_crl_pem(auth_client, ca['id']))
        for entry in full:
            ext = _ext_or_none(entry, CRLEntryExtensionOID.CRL_REASON)
            if ext:
                assert ext.value.reason != x509.ReasonFlags.remove_from_crl

        # Delta after a new base: plant revocation after base thisUpdate
        with app.app_context():
            from models import Certificate, db
            from models.crl import CRLMetadata
            base = CRLMetadata.query.filter_by(ca_id=ca['id'], is_delta=False).order_by(
                CRLMetadata.crl_number.desc()).first()
            row = Certificate.query.filter_by(caref=caref, revoked=True).order_by(
                Certificate.id.desc()).first()
            row.revoke_reason = 'removeFromCRL'
            row.revoked_at = base.this_update + timedelta(minutes=1)
            db.session.commit()

        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/delta/regenerate').status_code == 200
        delta = _load_crl(_fetch_crl_pem(auth_client, ca['id'], delta=True))
        delta_reasons = [
            e.value.reason
            for entry in delta
            if (e := _ext_or_none(entry, CRLEntryExtensionOID.CRL_REASON))
        ]
        assert x509.ReasonFlags.remove_from_crl in delta_reasons


class TestRfc5280AkiSmoke:
    """§5.2.1 smoke — intermediate CRL AKI still equals signing CA SKI."""

    def test_intermediate_crl_aki_equals_ski(self, app, auth_client, create_ca):
        _, inter = _make_intermediate(
            auth_client, create_ca, 'RFC AKI Root', 'RFC AKI Intermediate')
        assert auth_client.post(f'{CRL_BASE}/{inter["id"]}/regenerate').status_code == 200
        crl = _load_crl(_fetch_crl_pem(auth_client, inter['id']))
        with app.app_context():
            from models import CA, db
            ca = db.session.get(CA, inter['id'])
            ca_cert = x509.load_pem_x509_certificate(
                base64.b64decode(ca.crt), default_backend())
        crl_aki = crl.extensions.get_extension_for_oid(
            ExtensionOID.AUTHORITY_KEY_IDENTIFIER).value.key_identifier
        ski = ca_cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_KEY_IDENTIFIER).value.digest
        ca_aki = ca_cert.extensions.get_extension_for_oid(
            ExtensionOID.AUTHORITY_KEY_IDENTIFIER).value.key_identifier
        assert crl_aki == ski
        assert crl_aki != ca_aki
        assert crl.is_signature_valid(ca_cert.public_key())


class TestCrlReasonHelperUnit:
    def test_apply_revoke_reason_matrix(self):
        from services.crl.generation import _apply_revoke_reason

        b = x509.RevokedCertificateBuilder().serial_number(1).revocation_date(utc_now())
        out = _apply_revoke_reason(b, 'unspecified', is_delta=False).build()
        assert _ext_or_none(out, CRLEntryExtensionOID.CRL_REASON) is None

        b = x509.RevokedCertificateBuilder().serial_number(2).revocation_date(utc_now())
        out = _apply_revoke_reason(b, 'removeFromCRL', is_delta=False).build()
        assert _ext_or_none(out, CRLEntryExtensionOID.CRL_REASON) is None

        b = x509.RevokedCertificateBuilder().serial_number(3).revocation_date(utc_now())
        out = _apply_revoke_reason(b, 'removeFromCRL', is_delta=True).build()
        ext = _ext_or_none(out, CRLEntryExtensionOID.CRL_REASON)
        assert ext is not None
        assert ext.value.reason == x509.ReasonFlags.remove_from_crl

        b = x509.RevokedCertificateBuilder().serial_number(4).revocation_date(utc_now())
        out = _apply_revoke_reason(b, 'superseded', is_delta=False).build()
        assert out.extensions.get_extension_for_oid(
            CRLEntryExtensionOID.CRL_REASON).value.reason == x509.ReasonFlags.superseded


class TestCrlSecurityAuth:
    def test_regenerate_requires_auth(self, client):
        assert client.post(f'{CRL_BASE}/1/regenerate').status_code == 401

    def test_delta_regenerate_requires_auth(self, client):
        assert client.post(f'{CRL_BASE}/1/delta/regenerate').status_code == 401

    def test_get_crl_requires_auth(self, client):
        assert client.get(f'{CRL_BASE}/1').status_code == 401


class TestCrlLabOpensslText:
    """Lab-style: openssl crl -text shows AKI / CRL Number / no IDP on delta."""

    def test_openssl_text_full_and_delta(self, app, auth_client, create_ca):
        import subprocess
        import tempfile

        ca = create_ca(cn='OpenSSL Lab CA')
        _enable_delta(app, ca['id'])
        _issue_and_revoke(auth_client, ca['id'], 'openssl.lab.test', 'keyCompromise')
        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/regenerate').status_code == 200
        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/delta/regenerate').status_code == 200

        for delta in (False, True):
            pem = _fetch_crl_pem(auth_client, ca['id'], delta=delta)
            with tempfile.NamedTemporaryFile('w', suffix='.crl', delete=False) as f:
                f.write(pem)
                path = f.name
            try:
                out = subprocess.run(
                    ['openssl', 'crl', '-in', path, '-text', '-noout'],
                    capture_output=True, text=True, check=True,
                ).stdout
            finally:
                os.unlink(path)

            assert 'X509v3 Authority Key Identifier' in out
            assert 'X509v3 CRL Number' in out
            if delta:
                assert 'Delta CRL Indicator' in out
                assert 'Freshest CRL' not in out
            else:
                assert 'Freshest CRL' in out
