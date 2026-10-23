"""Regression tests for the medium/low findings of the v2.203 security audit.

  #8  mTLS certificate issuance was reachable by read-only roles, and fell back
      to an arbitrary CA (possibly the root) when no mTLS CA was configured.
  #9  API-key permissions were read verbatim from the mint-time snapshot, so a
      key kept scopes its owner had lost on demotion.
  #10 The unauthenticated /tsa endpoint signs with the CA key when configured
      with a CA certificate; operators now have a switch to refuse that.
  #13 The authenticated, state-changing mTLS enroll routes were CSRF-exempt.
  #15 Caller-supplied SSH certificate extensions were applied verbatim.
  low The OCSP nonce length was unbounded (RFC 8954 §2.1 allows 1..32 octets).

Follow-ups to the #246 fixes (audited after merge):
  #8  an explicit ca_id still directed ANY CA with only
      write:user_certificates; overriding the configured mTLS CA now
      requires write:cas.
  #9  the re-binding zeroed out category-wildcard keys ('read:*') after an
      owner demotion, because named roles hold only concrete scopes; they now
      expand to the owner's current scopes in that category.
  #10 the tsa_require_dedicated_cert switch was settable only by editing the
      SystemConfig row directly; it is now exposed in GET/PATCH
      /api/v2/tsa/config (default unchanged: off).
  #15 an explicitly emptied default_extensions policy ([]) was stored as
      NULL and re-inflated to the full standard set — allow-everything.
"""
import json

import pytest


# ---------------------------------------------------------------------------
# #8 — mTLS issuance requires an issuance scope
# ---------------------------------------------------------------------------

class TestMtlsIssuanceScope:
    def test_viewer_cannot_make_a_ca_sign_an_mtls_cert(self, viewer_client):
        r = viewer_client.post(
            '/api/v2/mtls/certificates',
            data=json.dumps({'name': 'viewer-probe'}),
            content_type='application/json',
        )
        assert r.status_code == 403, (
            f'read-only role obtained a CA-signed certificate: {r.data!r}'
        )

    def test_route_declares_an_issuance_permission(self):
        """The decorator must carry a scope, not a bare @require_auth()."""
        import inspect

        import api.v2.mtls as mtls_module

        source = inspect.getsource(mtls_module)
        marker = source.index('def create_mtls_certificate')
        decorators = source[:marker]
        # The decorator immediately preceding the handler must name a scope.
        last_require = decorators.rindex('@require_auth')
        assert decorators[last_require:].startswith("@require_auth(['"), (
            'create_mtls_certificate is guarded by a bare @require_auth()'
        )


# ---------------------------------------------------------------------------
# #8 follow-up — an explicit ca_id may not direct an arbitrary CA
# ---------------------------------------------------------------------------

class TestMtlsExplicitCaRequiresCaScope:
    """write:user_certificates alone must not direct ANY CA (root included).

    The #246 fix removed the CA.query.first() fallback but left the explicit
    path open: any holder of write:user_certificates — every operator by
    role, and grantable to any user through groups — could pass a ca_id
    naming any CA row and have it sign an auto-enrolled client certificate.
    Overriding the configured mTLS CA now requires write:cas.
    """

    @pytest.fixture()
    def mtls_cas(self, app, create_ca):
        """Two CAs; the first is configured as the trusted mTLS CA."""
        mtls_ca = create_ca(cn='mTLS Trusted CA probe')
        other_ca = create_ca(cn='Root Directed CA probe')

        from models import SystemConfig, db

        with app.app_context():
            row = SystemConfig.query.filter_by(key='mtls_trusted_ca_id').first()
            if not row:
                row = SystemConfig(key='mtls_trusted_ca_id')
                db.session.add(row)
            row.value = mtls_ca['refid']
            db.session.commit()

        yield {'mtls': mtls_ca, 'other': other_ca}

        with app.app_context():
            SystemConfig.query.filter_by(key='mtls_trusted_ca_id').delete(
                synchronize_session=False
            )
            # These tests enroll real client certificates, including one for
            # the admin. The database is session-scoped, so leaving them
            # behind makes `test_mtls.py::test_require_mtls_without_admin_cert`
            # pass its "at least one admin has an enrolled cert" guard and get
            # 200 where it asserts 400.
            from models import AuthCertificate
            AuthCertificate.query.filter(
                AuthCertificate.name.in_((
                    'ca-direct-probe',
                    'trusted-ca-probe',
                    'admin-ca-choice-probe',
                ))
            ).delete(synchronize_session=False)
            db.session.commit()

    def _group_granted_client(self, app, auth_client):
        """A viewer holding write:user_certificates via group membership —
        the least-privileged principal that can reach the route at all."""
        username = 'mtls_ca_direct_probe'
        r = auth_client.post(
            '/api/v2/users',
            data=json.dumps({
                'username': username,
                'password': 'ProbePass123!',
                'email': f'{username}@test.local',
                'role': 'viewer',
            }),
            content_type='application/json',
        )
        assert r.status_code in (200, 201, 409), r.data
        user_id = (json.loads(r.data).get('data') or json.loads(r.data)).get('id')

        r = auth_client.post(
            '/api/v2/groups',
            data=json.dumps({
                'name': 'mtls-issue-probe',
                'description': 'grants self-service mTLS issuance',
                'permissions': ['write:user_certificates',
                                'read:user_certificates'],
            }),
            content_type='application/json',
        )
        assert r.status_code in (200, 201, 409), r.data
        if r.status_code in (200, 201):
            group_id = (json.loads(r.data).get('data')
                        or json.loads(r.data)).get('id')
            r = auth_client.post(
                f'/api/v2/groups/{group_id}/members',
                data=json.dumps({'user_id': user_id}),
                content_type='application/json',
            )
            assert r.status_code in (200, 201, 409), r.data

        c = app.test_client()
        r = c.post(
            '/api/v2/auth/login',
            data=json.dumps({'username': username,
                             'password': 'ProbePass123!'}),
            content_type='application/json',
        )
        assert r.status_code == 200, r.data
        return c

    def test_foreign_ca_id_needs_write_cas(self, app, auth_client, mtls_cas):
        c = self._group_granted_client(app, auth_client)
        r = c.post(
            '/api/v2/mtls/certificates',
            data=json.dumps({'name': 'ca-direct-probe',
                             'ca_id': mtls_cas['other']['id']}),
            content_type='application/json',
        )
        assert r.status_code == 403, (
            f'write:user_certificates alone directed a non-mTLS CA: {r.data!r}'
        )

    def test_configured_mtls_ca_still_selectable_explicitly(
            self, app, auth_client, mtls_cas):
        """Passing the configured CA's own id stays allowed (API clients pin it)."""
        c = self._group_granted_client(app, auth_client)
        r = c.post(
            '/api/v2/mtls/certificates',
            data=json.dumps({'name': 'trusted-ca-probe',
                             'ca_id': mtls_cas['mtls']['refid']}),
            content_type='application/json',
        )
        assert r.status_code in (200, 201), r.data

    def test_admin_keeps_directing_any_ca(self, auth_client, mtls_cas):
        """The admin flow (Users page issues for a chosen CA) is unchanged."""
        r = auth_client.post(
            '/api/v2/mtls/certificates',
            data=json.dumps({'name': 'admin-ca-choice-probe',
                             'ca_id': mtls_cas['other']['id']}),
            content_type='application/json',
        )
        assert r.status_code in (200, 201), r.data


# ---------------------------------------------------------------------------
# #9 — API-key scopes are re-bound to the owner's current permissions
# ---------------------------------------------------------------------------

def _mint_api_key_row(username, permissions):
    """Insert an APIKey row directly (must run inside an app context).

    Bypasses the minting endpoint's you-can-only-grant-what-you-hold check on
    purpose: the stored permissions model a snapshot taken while the owner was
    MORE privileged (e.g. an admin since demoted), which is exactly the state
    the auth-time re-binding must handle. Returns the plaintext key.
    """
    import hashlib
    import secrets

    from models import User, db
    from models.api_key import APIKey

    user = User.query.filter_by(username=username).first()
    assert user is not None, f'test user {username} missing'
    key = f"ucm_ak_{secrets.token_urlsafe(32)}"
    row = APIKey(
        user_id=user.id,
        key_hash=hashlib.sha256(key.encode()).hexdigest(),
        key_prefix=key[:12],
        name=f'{username}-probe-key',
        permissions=json.dumps(permissions),
    )
    db.session.add(row)
    db.session.commit()
    return key


class TestApiKeyPermissionsFollowOwnerRole:
    def test_key_loses_scopes_when_owner_is_demoted(self, app, auth_client):
        username = 'apikey_demotion_probe'
        r = auth_client.post(
            '/api/v2/users',
            data=json.dumps({
                'username': username,
                'password': 'ProbePass123!',
                'email': f'{username}@test.local',
                'role': 'operator',
            }),
            content_type='application/json',
        )
        assert r.status_code in (200, 201, 409), r.data
        user_id = (json.loads(r.data).get('data') or json.loads(r.data)).get('id')

        owner = app.test_client()
        r = owner.post(
            '/api/v2/auth/login',
            data=json.dumps({'username': username, 'password': 'ProbePass123!'}),
            content_type='application/json',
        )
        assert r.status_code == 200, r.data

        # Operator legitimately holds write:cas at mint time.
        r = owner.post(
            '/api/v2/account/apikeys',
            data=json.dumps({
                'name': 'demotion-probe',
                'permissions': ['read:cas', 'write:cas'],
            }),
            content_type='application/json',
        )
        assert r.status_code in (200, 201), r.data
        api_key = (json.loads(r.data).get('data') or json.loads(r.data)).get('key')

        from auth.unified import AuthManager

        with app.app_context():
            before = AuthManager().verify_api_key(api_key)
        assert before is not None
        assert 'write:cas' in before['permissions']

        # Demote the owner to viewer (read-only).
        r = auth_client.put(
            f'/api/v2/users/{user_id}',
            data=json.dumps({'role': 'viewer'}),
            content_type='application/json',
        )
        assert r.status_code in (200, 204), r.data

        with app.app_context():
            after = AuthManager().verify_api_key(api_key)
        assert after is not None, 'key should still authenticate'
        assert 'write:cas' not in after['permissions'], (
            'API key kept write:cas after its owner was demoted to viewer'
        )

    def test_key_cannot_exceed_owner_via_wildcard(self, app, auth_client):
        """A '*' key is worth its owner's current scopes, not everything.

        Mints a key whose stored permissions are '["*"]' — the snapshot of a
        formerly privileged owner — for a user who is now a viewer, and runs
        it through verify_api_key. Asserts the wildcard branch replaces the
        stored '*' with exactly the owner's current effective permissions.
        """
        username = 'apikey_wildcard_probe'
        r = auth_client.post(
            '/api/v2/users',
            data=json.dumps({
                'username': username,
                'password': 'ProbePass123!',
                'email': f'{username}@test.local',
                'role': 'viewer',
            }),
            content_type='application/json',
        )
        assert r.status_code in (200, 201, 409), r.data

        from auth.permissions import get_effective_permissions
        from auth.unified import AuthManager
        from models import User

        with app.app_context():
            key = _mint_api_key_row(username, ['*'])
            result = AuthManager().verify_api_key(key)
            expected = get_effective_permissions(
                User.query.filter_by(username=username).first()
            )

        assert result is not None, 'the key itself must still authenticate'
        assert '*' not in result['permissions'], (
            "a '*' key kept the admin wildcard although its owner is a viewer"
        )
        assert 'write:cas' not in result['permissions']
        assert sorted(result['permissions']) == sorted(expected), (
            "a '*' key must be worth exactly the owner's current scopes"
        )

    def test_category_wildcard_key_tracks_owner_scopes(self, app, auth_client):
        """A ['read:*', 'write:*'] key of a demoted admin keeps the owner's
        current read/write scopes — it must not be zeroed out.

        This is the exact shape the UI mints (AccountPage scope presets
        'read' -> ['read:*'], 'readwrite' -> ['read:*', 'write:*']), and only
        admins can mint it. Named roles hold only concrete scopes, so an
        intersection by literal has_permission() matching drops every scope
        after the demotion the re-binding was built for: the key would
        authenticate with permissions=[] and 403 on everything.
        """
        username = 'apikey_catwildcard_probe'
        r = auth_client.post(
            '/api/v2/users',
            data=json.dumps({
                'username': username,
                'password': 'ProbePass123!',
                'email': f'{username}@test.local',
                'role': 'admin',
            }),
            content_type='application/json',
        )
        assert r.status_code in (200, 201, 409), r.data
        user_id = (json.loads(r.data).get('data') or json.loads(r.data)).get('id')

        with app.app_context():
            # Minted while the owner was an admin (the only role the minting
            # endpoint lets store category wildcards).
            key = _mint_api_key_row(username, ['read:*', 'write:*'])

        # Demote the owner to operator.
        r = auth_client.put(
            f'/api/v2/users/{user_id}',
            data=json.dumps({'role': 'operator'}),
            content_type='application/json',
        )
        assert r.status_code in (200, 204), r.data

        from auth.permissions import get_effective_permissions
        from auth.unified import AuthManager
        from models import User

        with app.app_context():
            result = AuthManager().verify_api_key(key)
            owner_perms = get_effective_permissions(
                User.query.filter_by(username=username).first()
            )

        assert result is not None, 'the key itself must still authenticate'
        got = set(result['permissions'])
        assert got, (
            'category-wildcard key was zeroed out by the demotion — the '
            "owner legitimately retains the operator read/write scopes"
        )
        expected = {
            p for p in owner_perms
            if p.split(':', 1)[0] in ('read', 'write')
        }
        assert got == expected, (
            f'expected the owner\'s current read/write scopes, got {sorted(got)}'
        )
        # The wildcard must never widen: no delete/admin scopes, no literal
        # wildcards, nothing the owner does not currently hold.
        assert 'read:*' not in got and 'write:*' not in got and '*' not in got
        assert not any(p.startswith(('delete:', 'admin:')) for p in got)


# ---------------------------------------------------------------------------
# #10 — TSA may be told to refuse signing with a CA certificate
# ---------------------------------------------------------------------------

class TestTsaDedicatedCertificateSwitch:
    def _ca_cert(self):
        from datetime import datetime, timedelta, timezone

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(65537, 2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'TSA CA')])
        cert = (x509.CertificateBuilder()
                .subject_name(name).issuer_name(name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
                .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None),
                               critical=True)
                .sign(key, hashes.SHA256()))
        return cert

    def test_ca_cert_accepted_by_default(self, app):
        """Backward compatibility: pre-2.200 deployments keep working."""
        from services.tsa_service import TSAService

        with app.app_context():
            TSAService.validate_certificate(self._ca_cert())  # must not raise

    def test_ca_cert_refused_when_dedicated_cert_required(self, app, monkeypatch):
        from services.tsa_service import TSAConfigurationError, TSAService

        monkeypatch.setattr(
            TSAService, '_require_dedicated_tsa_cert', staticmethod(lambda: True)
        )
        with app.app_context():
            with pytest.raises(TSAConfigurationError, match='dedicated'):
                TSAService.validate_certificate(self._ca_cert())


# ---------------------------------------------------------------------------
# #10 follow-up — the dedicated-cert switch is settable through the API
# ---------------------------------------------------------------------------

class TestTsaDedicatedCertToggleIsExposed:
    """tsa_require_dedicated_cert must be operable without editing the DB.

    The #246 review accepted the switch itself but flagged that it appeared
    in neither GET nor PATCH /api/v2/tsa/config (nor the UI), so as shipped
    it was settable only by inserting the SystemConfig row by hand — the
    service even instructs operators to "set tsa_require_dedicated_cert=true"
    with no supported way to do it.
    """

    @pytest.fixture()
    def clean_toggle_row(self, app):
        """Drop the toggle row afterwards: the DB is session-scoped, and the
        TestTsaDedicatedCertificateSwitch default-behaviour test (and any real
        signing test) must keep seeing the compatible default."""
        yield
        from models import SystemConfig, db

        with app.app_context():
            SystemConfig.query.filter_by(
                key='tsa_require_dedicated_cert'
            ).delete(synchronize_session=False)
            db.session.commit()

    def test_get_exposes_the_toggle_with_its_default(self, auth_client):
        r = auth_client.get('/api/v2/tsa/config')
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        data = body.get('data') or body
        assert data.get('require_dedicated_cert') is False, (
            'GET /api/v2/tsa/config must expose require_dedicated_cert '
            f'(default off), got: {data!r}'
        )

    def test_patch_reaches_the_enforcement_read(
            self, app, auth_client, clean_toggle_row):
        from services.tsa_service import TSAService

        r = auth_client.patch(
            '/api/v2/tsa/config',
            data=json.dumps({'require_dedicated_cert': True}),
            content_type='application/json',
        )
        assert r.status_code == 200, r.data

        # The exact read TSAService performs at signing time must now flip —
        # this ties the API field to the enforcement, not just to an echo.
        with app.app_context():
            assert TSAService._require_dedicated_tsa_cert() is True

        r = auth_client.get('/api/v2/tsa/config')
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        assert (body.get('data') or body)['require_dedicated_cert'] is True

        # Switching it back off restores the pre-2.200-compatible default.
        r = auth_client.patch(
            '/api/v2/tsa/config',
            data=json.dumps({'require_dedicated_cert': False}),
            content_type='application/json',
        )
        assert r.status_code == 200, r.data
        with app.app_context():
            assert TSAService._require_dedicated_tsa_cert() is False


# ---------------------------------------------------------------------------
# #13 — the mTLS enroll routes are no longer CSRF-exempt
# ---------------------------------------------------------------------------

class TestMtlsEnrollNotCsrfExempt:
    @pytest.mark.parametrize('path', [
        '/api/v2/mtls/enroll',
        '/api/v2/mtls/enroll-import',
    ])
    def test_enroll_paths_are_not_exempt(self, path):
        from security.csrf import CSRFProtection

        assert not CSRFProtection.is_exempt(path), (
            f'{path} is authenticated and state-changing; exempting it lets a '
            'cross-site POST bind an attacker certificate to the victim account'
        )

    def test_genuinely_public_protocol_paths_stay_exempt(self):
        """Control: the protocol endpoints must keep their exemption."""
        from security.csrf import CSRFProtection

        assert CSRFProtection.is_exempt('/acme/new-order')
        assert CSRFProtection.is_exempt('/api/v2/auth/login')


# ---------------------------------------------------------------------------
# #15 — SSH certificate extensions are constrained by the CA's policy
# ---------------------------------------------------------------------------

def _client_pubkey():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    key = ed25519.Ed25519PrivateKey.generate()
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode()


class TestSshExtensionAllowList:
    def _ca(self, descr, extensions=None):
        from services.ssh_ca_service import SSHCAService

        ca = SSHCAService.create_ca(
            descr=descr, ca_type='user', key_type='ed25519', username='t',
            allow_any_principal=True,
        )
        if extensions is not None:
            from models import db
            ca.set_default_extensions(extensions)
            db.session.commit()
        return ca

    def test_requested_extension_outside_ca_policy_is_refused(self, app):
        from services.ssh_cert import SSHCertificateService

        with app.app_context():
            ca = self._ca('Ext Policy CA', extensions=['permit-pty'])
            with pytest.raises(ValueError, match='not permitted'):
                SSHCertificateService.sign_certificate(
                    ca.id, _client_pubkey(), 'user', ['alice'],
                    validity_seconds=3600,
                    extensions=['permit-pty', 'permit-port-forwarding'],
                )

    def test_requested_extension_within_ca_policy_is_allowed(self, app):
        from services.ssh_cert import SSHCertificateService

        with app.app_context():
            ca = self._ca(
                'Ext Allow CA', extensions=['permit-pty', 'permit-port-forwarding']
            )
            cert = SSHCertificateService.sign_certificate(
                ca.id, _client_pubkey(), 'user', ['alice'],
                validity_seconds=3600,
                extensions=['permit-port-forwarding'],
            )
            assert cert.id is not None

    def test_default_extensions_still_apply_when_none_requested(self, app):
        from services.ssh_cert import SSHCertificateService

        with app.app_context():
            ca = self._ca('Ext Default CA', extensions=['permit-pty'])
            cert = SSHCertificateService.sign_certificate(
                ca.id, _client_pubkey(), 'user', ['alice'],
                validity_seconds=3600,
            )
            assert cert.id is not None

    def test_explicitly_empty_policy_refuses_every_extension(self, app):
        """An admin clearing the policy to [] means "nothing permitted".

        set_default_extensions([]) used to store NULL, which the getter
        re-inflated to the full standard set — permit-port-forwarding and
        permit-agent-forwarding included — silently turning the strictest
        possible policy into the most permissive one.
        """
        from services.ssh_cert import SSHCertificateService

        with app.app_context():
            ca = self._ca('Ext Empty CA', extensions=[])
            with pytest.raises(ValueError, match='not permitted'):
                SSHCertificateService.sign_certificate(
                    ca.id, _client_pubkey(), 'user', ['alice'],
                    validity_seconds=3600,
                    extensions=['permit-port-forwarding'],
                )

    def test_explicitly_empty_policy_issues_extensionless_certs(self, app):
        """With an explicit [] policy, the default-application path grants
        nothing either: the issued certificate carries zero extensions."""
        from services.ssh_cert import SSHCertificateService

        with app.app_context():
            ca = self._ca('Ext Empty Default CA', extensions=[])
            cert = SSHCertificateService.sign_certificate(
                ca.id, _client_pubkey(), 'user', ['alice'],
                validity_seconds=3600,
            )
            assert cert.get_extensions() == {}

    def test_unset_policy_keeps_the_standard_set(self, app):
        """Compatibility guard: a CA whose default_extensions column was
        never configured (NULL — every CA created before the policy existed)
        keeps applying AND allowing the standard OpenSSH set."""
        from models import db
        from models.ssh import SSHCertificateAuthority
        from services.ssh_cert import SSHCertificateService

        with app.app_context():
            ca = self._ca('Ext Unset CA')
            # Simulate the pre-existing row: column never populated.
            ca.default_extensions = None
            db.session.commit()

            assert (ca.get_default_extensions()
                    == list(SSHCertificateAuthority.STANDARD_EXTENSIONS))
            cert = SSHCertificateService.sign_certificate(
                ca.id, _client_pubkey(), 'user', ['alice'],
                validity_seconds=3600,
                extensions=['permit-pty'],
            )
            assert 'permit-pty' in cert.get_extensions()


# ---------------------------------------------------------------------------
# low — OCSP nonce length bounds (RFC 8954 §2.1)
# ---------------------------------------------------------------------------

class TestOcspNonceBounds:
    def _request_with_nonce(self, nonce_bytes):
        """Build a DER OCSPRequest carrying a nonce of the given length."""
        from asn1crypto import core, ocsp as asn1_ocsp

        cert_id = asn1_ocsp.CertId({
            'hash_algorithm': {'algorithm': 'sha1'},
            'issuer_name_hash': b'\x00' * 20,
            'issuer_key_hash': b'\x00' * 20,
            'serial_number': 1,
        })
        request = asn1_ocsp.Request({'req_cert': cert_id})
        ext = asn1_ocsp.TBSRequestExtension({
            'extn_id': '1.3.6.1.5.5.7.48.1.2',
            'critical': False,
            'extn_value': core.OctetString(nonce_bytes),
        })
        tbs = asn1_ocsp.TBSRequest({
            'request_list': asn1_ocsp.Requests([request]),
            'request_extensions': asn1_ocsp.TBSRequestExtensions([ext]),
        })
        return asn1_ocsp.OCSPRequest({'tbs_request': tbs}).dump()

    def test_oversized_nonce_is_rejected(self, app):
        """Parsing returns None, which the route turns into MALFORMED_REQUEST.

        Without the bound the 4 KiB nonce was echoed back into the signed
        response, letting a client inflate the CA's signing and bandwidth cost.
        """
        from services.ocsp_service import OCSPService

        der = self._request_with_nonce(b'\xAA' * 4096)
        with app.app_context():
            assert OCSPService().parse_request_details(der) is None

    def test_oversized_nonce_yields_malformed_response(self, app, client):
        """End-to-end: the endpoint refuses rather than signing the echo."""
        from cryptography.x509 import ocsp as x509_ocsp

        der = self._request_with_nonce(b'\xAA' * 4096)
        r = client.post(
            '/ocsp', data=der, content_type='application/ocsp-request'
        )
        assert r.status_code == 200
        response = x509_ocsp.load_der_ocsp_response(r.data)
        assert response.response_status == (
            x509_ocsp.OCSPResponseStatus.MALFORMED_REQUEST
        )

    def test_maximum_length_nonce_is_accepted(self, app):
        from services.ocsp_service import OCSPService

        der = self._request_with_nonce(b'\xAA' * 32)
        with app.app_context():
            parsed = OCSPService().parse_request_details(der)
        assert parsed is not None
        assert parsed.nonce == b'\xAA' * 32


# ---------------------------------------------------------------------------
# low — recovery codes survive the 2FA login length cap
# ---------------------------------------------------------------------------

class TestRecoveryCodeLengthCap:
    """A recovery code is XXXX-XXXX-XXXX-XXXX (19 chars).

    The login handler capped the submitted code at 10 characters before
    comparing, so every recovery code was truncated to 'XXXX-XXXX-' and could
    never match. This failed closed (no security hole) but made account
    recovery impossible.
    """

    def test_generated_code_is_longer_than_the_old_cap(self):
        import secrets

        code = '-'.join(secrets.token_hex(2).upper() for _ in range(4))
        assert len(code) == 19, code
        assert len(code) > 10, 'the old [:10] cap would truncate this'

    def test_login_handler_cap_admits_a_full_recovery_code(self):
        """The cap in the 2FA verify handler must exceed 19 characters."""
        import inspect
        import re

        import api.v2.auth_methods as auth_methods

        source = inspect.getsource(auth_methods)
        caps = [
            int(m) for m in
            re.findall(r"str\(data\['code'\]\)\.strip\(\)\.upper\(\)\[:(\d+)\]", source)
        ]
        assert caps, 'could not locate the 2FA code length cap'
        for cap in caps:
            assert cap >= 19, (
                f'2FA code truncated to {cap} chars — a 19-char recovery code '
                'can never match'
            )

    def test_full_length_code_round_trips_through_consume(self, app):
        """End-to-end: a full 19-char code is accepted and consumed once."""
        import json as _json
        import secrets

        from models import User, db
        from utils.backup_codes import consume_code

        code = '-'.join(secrets.token_hex(2).upper() for _ in range(4))
        with app.app_context():
            user = User(
                username=f'recovery_probe_{secrets.token_hex(4)}',
                email='recovery@test.local',
                password_hash='!',
                role='viewer',
                active=True,
                backup_codes=_json.dumps([code]),
            )
            db.session.add(user)
            db.session.commit()

            # The value the handler would compare after its length cap.
            submitted = code.strip().upper()[:32]
            assert consume_code(user, submitted) is True
            db.session.commit()
            # Single-use: a replay must fail.
            assert consume_code(user, submitted) is False
