"""
Regression tests for issue #202 / RFC 5280 §5.2.1.

CRL Authority Key Identifier MUST identify the key that signed the CRL,
i.e. the issuing CA's Subject Key Identifier — NOT the AKI copied from the
issuing CA certificate (which points at the parent for intermediates).

Bug trigger: Intermediate CA where ca.AKI != ca.SKI. Old code preferred
ca.AKI, so clients matching CRL AKI to the intermediate SKI failed path
building / rejected the CRL.
"""
import base64
import json
import os
import sys

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID

from tests.conftest import assert_success, get_json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTENT_JSON = 'application/json'
CRL_BASE = '/api/v2/crl'


def _post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


def _load_ca_cert(app, ca_id):
    from models import CA, db
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        assert ca is not None
        pem = base64.b64decode(ca.crt)
        return x509.load_pem_x509_certificate(pem, default_backend())


def _ext(cert_or_crl, oid):
    return cert_or_crl.extensions.get_extension_for_oid(oid).value


def _crl_from_pem(pem: str):
    return x509.load_pem_x509_crl(
        pem.encode() if isinstance(pem, str) else pem,
        default_backend(),
    )


def _fetch_crl_pem(auth_client, ca_id, *, delta=False):
    url = f'{CRL_BASE}/{ca_id}/delta' if delta else f'{CRL_BASE}/{ca_id}'
    r = auth_client.get(url)
    assert r.status_code == 200, r.data
    data = get_json(r).get('data', get_json(r))
    pem = data.get('crl_pem')
    assert pem, f'No crl_pem in GET {url}: {data}'
    return pem


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
    inter = assert_success(r, status=201)
    return root, inter


class TestCrlAkiMatchesIssuingCaSki:
    """Issue #202 — full CRL AKI == issuing CA SKI."""

    def test_intermediate_precondition_aki_differs_from_ski(self, app, auth_client, create_ca):
        """Without this split the bug is invisible on self-signed roots."""
        _, inter = _make_intermediate(
            auth_client, create_ca, 'AKI-Pre Root', 'AKI-Pre Intermediate')
        ca_cert = _load_ca_cert(app, inter['id'])
        ski = _ext(ca_cert, ExtensionOID.SUBJECT_KEY_IDENTIFIER).digest
        aki = _ext(ca_cert, ExtensionOID.AUTHORITY_KEY_IDENTIFIER).key_identifier
        assert aki is not None
        assert aki != ski, (
            'Test setup broken: intermediate AKI equals SKI — '
            'cannot detect the #202 copy-AKI bug'
        )

    def test_full_crl_aki_equals_intermediate_ski_not_parent(self, app, auth_client, create_ca):
        root, inter = _make_intermediate(
            auth_client, create_ca, 'AKI-Full Root', 'AKI-Full Intermediate')

        r = auth_client.post(f'{CRL_BASE}/{inter["id"]}/regenerate')
        assert r.status_code == 200, r.data
        crl = _crl_from_pem(_fetch_crl_pem(auth_client, inter['id']))

        inter_cert = _load_ca_cert(app, inter['id'])
        root_cert = _load_ca_cert(app, root['id'])

        crl_aki = _ext(crl, ExtensionOID.AUTHORITY_KEY_IDENTIFIER).key_identifier
        inter_ski = _ext(inter_cert, ExtensionOID.SUBJECT_KEY_IDENTIFIER).digest
        inter_aki = _ext(inter_cert, ExtensionOID.AUTHORITY_KEY_IDENTIFIER).key_identifier
        root_ski = _ext(root_cert, ExtensionOID.SUBJECT_KEY_IDENTIFIER).digest

        # Contract: CRL AKI == signing CA SKI (RFC 5280 §5.2.1)
        assert crl_aki == inter_ski
        # Old buggy path copied the CA certificate's AKI (parent key id)
        assert crl_aki != inter_aki
        assert crl_aki != root_ski

        assert crl.is_signature_valid(inter_cert.public_key())

    def test_root_crl_aki_equals_root_ski(self, app, auth_client, create_ca):
        root = create_ca(cn='AKI-Root Only')
        r = auth_client.post(f'{CRL_BASE}/{root["id"]}/regenerate')
        assert r.status_code == 200, r.data
        crl = _crl_from_pem(_fetch_crl_pem(auth_client, root['id']))
        root_cert = _load_ca_cert(app, root['id'])
        crl_aki = _ext(crl, ExtensionOID.AUTHORITY_KEY_IDENTIFIER).key_identifier
        root_ski = _ext(root_cert, ExtensionOID.SUBJECT_KEY_IDENTIFIER).digest
        assert crl_aki == root_ski
        assert crl.is_signature_valid(root_cert.public_key())

    def test_delta_crl_aki_equals_intermediate_ski(self, app, auth_client, create_ca):
        _, inter = _make_intermediate(
            auth_client, create_ca, 'AKI-Delta Root', 'AKI-Delta Intermediate')

        with app.app_context():
            from models import CA, db
            ca = db.session.get(CA, inter['id'])
            ca.cdp_enabled = True
            ca.delta_crl_enabled = True
            ca.set_cdp_urls([f'http://cdp.test.local/cdp/{ca.refid}.crl'])
            db.session.commit()

        r = auth_client.post(f'{CRL_BASE}/{inter["id"]}/regenerate')
        assert r.status_code == 200, r.data

        r = auth_client.post(f'{CRL_BASE}/{inter["id"]}/delta/regenerate')
        assert r.status_code == 200, r.data
        crl = _crl_from_pem(_fetch_crl_pem(auth_client, inter['id'], delta=True))

        inter_cert = _load_ca_cert(app, inter['id'])
        crl_aki = _ext(crl, ExtensionOID.AUTHORITY_KEY_IDENTIFIER).key_identifier
        inter_ski = _ext(inter_cert, ExtensionOID.SUBJECT_KEY_IDENTIFIER).digest
        inter_aki = _ext(inter_cert, ExtensionOID.AUTHORITY_KEY_IDENTIFIER).key_identifier

        assert crl_aki == inter_ski
        assert crl_aki != inter_aki
        assert crl.extensions.get_extension_for_oid(ExtensionOID.DELTA_CRL_INDICATOR)
        assert crl.is_signature_valid(inter_cert.public_key())


class TestCrlAkiSecurityAndAuth:
    """Security / auth gates around CRL regenerate (unchanged by #202)."""

    def test_regenerate_requires_auth(self, client):
        assert client.post(f'{CRL_BASE}/1/regenerate').status_code == 401

    def test_delta_regenerate_requires_auth(self, client):
        assert client.post(f'{CRL_BASE}/1/delta/regenerate').status_code == 401


class TestCrlAkiServiceFallback:
    """Unit-level: SKI missing → derive AKI from issuing CA public key."""

    def test_generate_crl_without_ski_uses_public_key(self, app, auth_client, create_ca, monkeypatch):
        root = create_ca(cn='AKI-Fallback Root')
        from cryptography.x509.oid import ExtensionOID as EOID
        from cryptography import x509 as cx509

        real_get = cx509.Extensions.get_extension_for_oid

        def fake_get(self, oid):
            if oid == EOID.SUBJECT_KEY_IDENTIFIER:
                raise cx509.ExtensionNotFound('ski', oid)
            return real_get(self, oid)

        monkeypatch.setattr(cx509.Extensions, 'get_extension_for_oid', fake_get)

        with app.app_context():
            from services.crl_service import CRLService
            from models import CA, db
            meta = CRLService.generate_crl(root['id'], username='test')
            assert meta.crl_pem
            crl = _crl_from_pem(meta.crl_pem)
            ca = db.session.get(CA, root['id'])
            ca_cert = x509.load_pem_x509_certificate(
                base64.b64decode(ca.crt), default_backend())
            expected = x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_cert.public_key()
            ).key_identifier
            got = _ext(crl, ExtensionOID.AUTHORITY_KEY_IDENTIFIER).key_identifier
            assert got == expected
