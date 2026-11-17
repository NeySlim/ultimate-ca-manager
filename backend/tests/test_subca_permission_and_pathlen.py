"""Regression tests: sub-CA minting via the CSR-sign endpoint
(security audit v2.203, item #4).

``POST /api/v2/csrs/<id>/sign`` is guarded by ['write:csrs',
'write:certificates'] but accepted cert_type='intermediate_ca', which creates a
full CA row with a signing key. Creating a CA normally requires 'write:cas', so
a principal holding only certificate/CSR scopes (e.g. a scoped API key) could
escalate to minting an intermediate able to issue for arbitrary names.

Separately, the child's pathLenConstraint was copied straight from the
requester's CSR BasicConstraints with no cap against the parent, so a signed
intermediate could claim a deeper — or unlimited — path than its issuer
(RFC 5280 §4.2.1.9).
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtensionOID, NameOID

from services.trust_store.trust_store_service import TrustStoreService


def _ca(path_length):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Pathlen CA')])
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=path_length),
                critical=True)
            .sign(key, hashes.SHA256()))
    return cert, key


def _subca_csr(path_length):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name(
                [x509.NameAttribute(NameOID.COMMON_NAME, 'sub.example.com')]))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=path_length),
                critical=True)
            .sign(key, hashes.SHA256()))


def _sign_subca(ca, csr):
    ca_cert, ca_key = ca
    pem = TrustStoreService.sign_csr(
        csr_pem=csr.public_bytes(serialization.Encoding.PEM),
        ca_cert=ca_cert,
        ca_private_key=ca_key,
        validity_days=30,
        cert_type='intermediate_ca',
    )
    return x509.load_pem_x509_certificate(pem)


def _path_length(cert):
    return cert.extensions.get_extension_for_oid(
        ExtensionOID.BASIC_CONSTRAINTS
    ).value.path_length


class TestSubCaPathLenCap:
    """RFC 5280 §4.2.1.9 — a child may assert at most parent_pathlen - 1."""

    def test_unlimited_request_is_clamped_to_parent(self):
        """CSR asks for an unconstrained path under a pathlen-2 parent."""
        cert = _sign_subca(_ca(path_length=2), _subca_csr(path_length=None))
        assert _path_length(cert) == 1

    def test_deeper_request_is_clamped_to_parent(self):
        cert = _sign_subca(_ca(path_length=2), _subca_csr(path_length=9))
        assert _path_length(cert) == 1

    def test_within_budget_request_is_honoured(self):
        cert = _sign_subca(_ca(path_length=3), _subca_csr(path_length=0))
        assert _path_length(cert) == 0

    def test_pathlen_zero_parent_cannot_issue_a_subca(self):
        """A parent with pathLen 0 may not be followed by another CA at all."""
        with pytest.raises(ValueError, match='pathLenConstraint 0'):
            _sign_subca(_ca(path_length=0), _subca_csr(path_length=None))

    def test_unconstrained_parent_honours_request(self):
        """No parent constraint — the child's own request stands."""
        cert = _sign_subca(_ca(path_length=None), _subca_csr(path_length=1))
        assert _path_length(cert) == 1

    # -- CSRs WITHOUT BasicConstraints: the shape UCM's own generator emits --
    #
    # The clamp above only ran inside the extension-copy loop, i.e. when the
    # CSR carried a BasicConstraints extension. TrustStoreService.generate_csr
    # emits none, so the default API path (POST /api/v2/csrs then sign as
    # intermediate_ca) took the "add basic extensions if not in CSR" branch,
    # which hardcoded pathLen 0 without ever consulting the parent — the
    # pathLen-0 refusal never fired on exactly the CSRs UCM itself produces.

    @staticmethod
    def _subca_csr_without_bc():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        return (x509.CertificateSigningRequestBuilder()
                .subject_name(x509.Name(
                    [x509.NameAttribute(NameOID.COMMON_NAME, 'sub.example.com')]))
                .sign(key, hashes.SHA256()))

    def test_pathlen_zero_parent_refuses_csr_without_basic_constraints(self):
        with pytest.raises(ValueError, match='pathLenConstraint 0'):
            _sign_subca(_ca(path_length=0), self._subca_csr_without_bc())

    def test_pathlen_one_parent_still_signs_csr_without_basic_constraints(self):
        """Control: the guard must not break the normal no-BC intermediate."""
        cert = _sign_subca(_ca(path_length=1), self._subca_csr_without_bc())
        assert _path_length(cert) == 0

    def test_unconstrained_parent_still_signs_csr_without_basic_constraints(self):
        cert = _sign_subca(_ca(path_length=None), self._subca_csr_without_bc())
        assert _path_length(cert) == 0


class TestCreateCaPathLenClamp:
    """The sibling sub-CA route must enforce the same RFC 5280 §4.2.1.9 rule.

    POST /api/v2/cas → create_internal_ca → create_ca_certificate took the
    user-supplied pathLength with only a 0..32 range check: a pathLen-0
    parent happily issued a child asserting pathLen 5, and omitting the field
    under a constrained parent produced an UNLIMITED child. Same permission
    level as the sign-CSR route, same object minted, no clamp — this class
    drives the certificate-creation mixin directly (the service layer clamps
    the stored CA row with the same helper).
    """

    @staticmethod
    def _create_child(parent, path_length):
        parent_cert, parent_key = parent
        child_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert_pem, _ = TrustStoreService.create_ca_certificate(
            subject=x509.Name(
                [x509.NameAttribute(NameOID.COMMON_NAME, 'Child CA')]),
            private_key=child_key,
            issuer=parent_cert.subject,
            issuer_private_key=parent_key,
            issuer_cert=parent_cert,
            validity_days=30,
            path_length=path_length,
        )
        return x509.load_pem_x509_certificate(cert_pem)

    def test_pathlen_zero_parent_refuses_child(self):
        with pytest.raises(ValueError, match='pathLenConstraint 0'):
            self._create_child(_ca(path_length=0), path_length=5)

    def test_deeper_request_is_clamped_to_parent(self):
        cert = self._create_child(_ca(path_length=2), path_length=9)
        assert _path_length(cert) == 1

    def test_unlimited_request_is_clamped_to_parent(self):
        """Omitting pathLength used to mint an UNLIMITED child under a
        constrained parent — the silent worst case."""
        cert = self._create_child(_ca(path_length=2), path_length=None)
        assert _path_length(cert) == 1

    def test_within_budget_request_is_honoured(self):
        cert = self._create_child(_ca(path_length=3), path_length=0)
        assert _path_length(cert) == 0

    def test_unconstrained_parent_honours_request(self):
        cert = self._create_child(_ca(path_length=None), path_length=5)
        assert _path_length(cert) == 5

    def test_root_creation_is_unaffected(self):
        """No issuer at all (a root) — the operator's choice stands."""
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert_pem, _ = TrustStoreService.create_ca_certificate(
            subject=x509.Name(
                [x509.NameAttribute(NameOID.COMMON_NAME, 'Standalone Root')]),
            private_key=key,
            validity_days=30,
            path_length=3,
        )
        assert _path_length(x509.load_pem_x509_certificate(cert_pem)) == 3


class TestSubCaRequiresWriteCas:
    """The CSR-sign endpoint must not be a back door around 'write:cas'."""

    _counter = 0

    def _make_csr_record(self, auth_client):
        """Create a pending CSR record (the API generates the key + CSR)."""
        TestSubCaRequiresWriteCas._counter += 1
        r = auth_client.post(
            '/api/v2/csrs',
            data=json.dumps({
                'cn': f'escalate{self._counter}.example.com',
                'organization': 'Test Org',
                'country': 'US',
                'key_type': 'RSA 2048',
            }),
            content_type='application/json',
        )
        assert r.status_code in (200, 201), r.data
        body = json.loads(r.data)
        return (body.get('data') or body).get('id')

    def _scoped_key(self, app, permissions, name):
        """Create an API key held by a dedicated operator user.

        The row is written directly rather than via POST
        /api/v2/account/apikeys: that endpoint enforces a
        10-active-keys-per-user cap that other tests consume in a full-suite
        run, and this test is about authorisation at the sign endpoint, not
        about key minting.

        The owner is an *operator* — who legitimately holds write:cas — while
        the key is scoped to certificate/CSR permissions only. That is exactly
        the escalation shape: a principal whose key omits write:cas must not be
        able to mint a CA.
        """
        import hashlib
        import secrets

        from models import User, db
        from models.api_key import APIKey

        username = f'subca_probe_{name}'
        with app.app_context():
            user = User.query.filter_by(username=username).first()
            if not user:
                user = User(
                    username=username,
                    email=f'{username}@test.local',
                    password_hash='!',           # unused: key auth only
                    role='operator',
                    active=True,
                )
                db.session.add(user)
                db.session.commit()

            raw_key = f'ucm_ak_{secrets.token_urlsafe(32)}'
            db.session.add(APIKey(
                user_id=user.id,
                key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
                key_prefix=raw_key[:12],
                name=name,
                permissions=json.dumps(permissions),
            ))
            db.session.commit()
        return raw_key

    def test_cert_scoped_key_cannot_mint_an_intermediate_ca(
        self, app, auth_client, create_ca
    ):
        """The escalation: CSR/cert scopes only, asking for intermediate_ca."""
        ca = create_ca(cn='Escalation Parent CA')
        csr_id = self._make_csr_record(auth_client)
        api_key = self._scoped_key(
            app,
            ['read:csrs', 'write:csrs', 'read:certificates', 'write:certificates'],
            'subca-escalation-probe',
        )

        client = app.test_client()
        r = client.post(
            f'/api/v2/csrs/{csr_id}/sign',
            data=json.dumps({
                'ca_id': ca['id'],
                'cert_type': 'intermediate_ca',
                'validity_days': 365,
            }),
            content_type='application/json',
            headers={'X-API-Key': api_key},
        )
        assert r.status_code == 403, (
            f'expected 403, got {r.status_code}: {r.data!r} — a key without '
            'write:cas minted an intermediate CA'
        )

    def test_cert_scoped_key_can_still_sign_a_leaf(
        self, app, auth_client, create_ca
    ):
        """Control: the gate must not break ordinary certificate signing."""
        ca = create_ca(cn='Leaf Signing Parent CA')
        csr_id = self._make_csr_record(auth_client)
        api_key = self._scoped_key(
            app,
            ['read:csrs', 'write:csrs', 'read:certificates', 'write:certificates'],
            'leaf-signing-probe',
        )

        client = app.test_client()
        r = client.post(
            f'/api/v2/csrs/{csr_id}/sign',
            data=json.dumps({
                'ca_id': ca['id'],
                'cert_type': 'server',
                'validity_days': 365,
            }),
            content_type='application/json',
            headers={'X-API-Key': api_key},
        )
        assert r.status_code in (200, 201), r.data

    def test_admin_can_still_mint_an_intermediate_ca(self, auth_client, create_ca):
        """Control: admin holds '*', so the CA path stays open to operators."""
        ca = create_ca(cn='Admin Subca Parent CA')
        csr_id = self._make_csr_record(auth_client)
        r = auth_client.post(
            f'/api/v2/csrs/{csr_id}/sign',
            data=json.dumps({
                'ca_id': ca['id'],
                'cert_type': 'intermediate_ca',
                'validity_days': 365,
            }),
            content_type='application/json',
        )
        assert r.status_code in (200, 201), r.data
