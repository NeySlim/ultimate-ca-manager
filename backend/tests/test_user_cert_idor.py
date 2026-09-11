"""
Tests for user certificate IDOR vulnerabilities.

Verifies that revoke and delete endpoints on /api/v2/user-certificates/<id>
enforce ownership checks via _can_access_cert().

NOTE: In the current permission model, only admin and operator roles have
write:user_certificates and delete:user_certificates. The _can_access_cert
function grants access to admin, operator, and auditor roles. So the
ownership check is defense-in-depth: it protects against future custom
roles that might have write:user_certificates without being operator/admin.

Tests cover:
- Admin can revoke/delete any cert (current behavior)
- Operator can revoke/delete any cert (current behavior)
- Owner can revoke/delete their own cert
- Defense-in-depth: a custom role with write:user_certificates but not
  operator/admin is blocked from cross-user access
- Non-existent cert returns 404
"""
import pytest
import json
import os
import sys

from tests.conftest import get_json, assert_success, assert_error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTENT_JSON = 'application/json'
BASE = '/api/v2/user-certificates'


_CERT_NAMES = (
    'Owner Cert', 'User A Cert', 'Admin Revoked Cert',
    'Delete Owner Cert', 'User A Delete Cert', 'Admin Deleted Cert',
    'Deep Revoke Cert', 'Deep Own Cert',
    'Deep Delete Cert', 'Deep Own Delete Cert',
)


@pytest.fixture(scope='module')
def mtls_ca(app, create_ca):
    """Create a CA and configure it as the trusted mTLS CA.

    Self-contained: creates its own CA via the API factory, saves and
    restores the original mtls_trusted_ca_id value, and cleans up the
    AuthCertificate rows created by these tests on teardown.
    """
    ca = create_ca(cn='mTLS IDOR Test CA')
    from models import SystemConfig, db
    from models import AuthCertificate
    with app.app_context():
        # Save original mtls_trusted_ca to restore later
        row = SystemConfig.query.filter_by(key='mtls_trusted_ca_id').first()
        orig_value = row.value if row else None
        if not row:
            row = SystemConfig(key='mtls_trusted_ca_id')
            db.session.add(row)
        row.value = ca['refid']
        db.session.commit()
    yield ca
    with app.app_context():
        # Restore original mtls_trusted_ca_id value (don't just delete it)
        SystemConfig.query.filter_by(key='mtls_trusted_ca_id').delete()
        if orig_value is not None:
            db.session.add(SystemConfig(
                key='mtls_trusted_ca_id',
                value=orig_value,
            ))
        # Delete only the AuthCertificate rows created by these tests
        AuthCertificate.query.filter(
            AuthCertificate.name.in_(_CERT_NAMES)
        ).delete(synchronize_session=False)
        db.session.commit()


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


def _login_as(app, username, password):
    """Log in and return an authenticated test client."""
    c = app.test_client()
    r = c.post('/api/v2/auth/login',
               data=json.dumps({'username': username, 'password': password}),
               content_type='application/json')
    assert r.status_code == 200, f'Login failed for {username}: {r.data}'
    return c


def _create_user_and_login(app, auth_client, create_user, username, role='operator'):
    """Create a user with the given role and return a logged-in client + user dict."""
    user = create_user(
        username=username,
        password='UserPass123!',
        email=f'{username}@test.local',
        role=role,
    )
    client = _login_as(app, username, 'UserPass123!')
    return client, user


def _create_mtls_cert_for_user(auth_client, user_id, name='Test Client Cert'):
    """Admin creates an mTLS certificate for a user. Returns the auth cert dict."""
    r = auth_client.post(
        f'/api/v2/users/{user_id}/mtls/certificates',
        data=json.dumps({'mode': 'generate', 'name': name}),
        content_type='application/json',
    )
    assert r.status_code in (200, 201), f'mTLS cert creation failed: {r.data}'
    data = json.loads(r.data)
    return data.get('data', data)


class TestUserCertIdorRevoke:
    """#8 — revoke_user_certificate must enforce ownership."""

    def test_owner_can_revoke_own_cert(self, app, auth_client, create_user, mtls_ca):
        """Operator can revoke their own certificate."""
        user_a_client, user_a = _create_user_and_login(
            app, auth_client, create_user, 'idor_revoke_owner'
        )
        cert = _create_mtls_cert_for_user(auth_client, user_a['id'], 'Owner Cert')
        cert_id = cert.get('id')

        r = post_json(user_a_client, f'{BASE}/{cert_id}/revoke', {'reason': 'unspecified'})
        assert r.status_code == 200, f'Owner should be able to revoke: {r.data}'

    def test_operator_can_revoke_any_cert(self, app, auth_client, create_user, mtls_ca):
        """Operator can revoke any user's certificate (by design — trusted role)."""
        _, user_a = _create_user_and_login(
            app, auth_client, create_user, 'idor_revoke_op_a'
        )
        user_b_client, _ = _create_user_and_login(
            app, auth_client, create_user, 'idor_revoke_op_b'
        )
        cert = _create_mtls_cert_for_user(auth_client, user_a['id'], 'User A Cert')
        cert_id = cert.get('id')

        r = post_json(user_b_client, f'{BASE}/{cert_id}/revoke', {'reason': 'unspecified'})
        assert r.status_code == 200, f'Operator should be able to revoke any cert: {r.data}'

    def test_admin_can_revoke_any_cert(self, app, auth_client, create_user, mtls_ca):
        """Admin can revoke any user's certificate."""
        _, user_a = _create_user_and_login(
            app, auth_client, create_user, 'idor_revoke_admin'
        )
        cert = _create_mtls_cert_for_user(auth_client, user_a['id'], 'Admin Revoked Cert')
        cert_id = cert.get('id')

        r = post_json(auth_client, f'{BASE}/{cert_id}/revoke', {'reason': 'keyCompromise'})
        assert r.status_code == 200, f'Admin should be able to revoke: {r.data}'

    def test_revoke_nonexistent_cert(self, auth_client):
        """Revoke non-existent cert returns 404."""
        r = post_json(auth_client, f'{BASE}/999999/revoke', {'reason': 'unspecified'})
        assert r.status_code == 404


class TestUserCertIdorDelete:
    """#9 — delete_user_certificate must enforce ownership."""

    def test_owner_can_delete_own_cert(self, app, auth_client, create_user, mtls_ca):
        """Operator can delete their own certificate."""
        user_a_client, user_a = _create_user_and_login(
            app, auth_client, create_user, 'idor_delete_owner'
        )
        cert = _create_mtls_cert_for_user(auth_client, user_a['id'], 'Delete Owner Cert')
        cert_id = cert.get('id')

        r = user_a_client.delete(f'{BASE}/{cert_id}')
        assert r.status_code == 204, f'Owner should be able to delete: {r.data}'

    def test_operator_can_delete_any_cert(self, app, auth_client, create_user, mtls_ca):
        """Operator can delete any user's certificate (by design — trusted role)."""
        _, user_a = _create_user_and_login(
            app, auth_client, create_user, 'idor_delete_op_a'
        )
        user_b_client, _ = _create_user_and_login(
            app, auth_client, create_user, 'idor_delete_op_b'
        )
        cert = _create_mtls_cert_for_user(auth_client, user_a['id'], 'User A Delete Cert')
        cert_id = cert.get('id')

        r = user_b_client.delete(f'{BASE}/{cert_id}')
        assert r.status_code == 204, f'Operator should be able to delete any cert: {r.data}'

    def test_admin_can_delete_any_cert(self, app, auth_client, create_user, mtls_ca):
        """Admin can delete any user's certificate."""
        _, user_a = _create_user_and_login(
            app, auth_client, create_user, 'idor_delete_admin'
        )
        cert = _create_mtls_cert_for_user(auth_client, user_a['id'], 'Admin Deleted Cert')
        cert_id = cert.get('id')

        r = auth_client.delete(f'{BASE}/{cert_id}')
        assert r.status_code == 204, f'Admin should be able to delete: {r.data}'

    def test_delete_nonexistent_cert(self, auth_client):
        """Delete non-existent cert returns 404."""
        r = auth_client.delete(f'{BASE}/999999')
        assert r.status_code == 404


class TestUserCertIdorDefenseInDepth:
    """#8-#9 — Defense-in-depth: verify _can_access_cert blocks cross-user access.

    Even if a future custom role has write:user_certificates but is not
    operator/admin/auditor, the ownership check should block cross-user
    access. We simulate this by monkeypatching _is_admin_or_operator and
    _is_auditor to return False for a specific user.
    """

    def test_custom_role_cannot_revoke_other_user_cert(
        self, app, auth_client, create_user, monkeypatch, mtls_ca
    ):
        """A non-operator user with write:user_certificates cannot revoke another's cert."""
        from api.v2 import user_certificates as uc_module

        _, user_a = _create_user_and_login(
            app, auth_client, create_user, 'idor_deep_revoke_a'
        )
        user_b_client, user_b = _create_user_and_login(
            app, auth_client, create_user, 'idor_deep_revoke_b'
        )
        cert = _create_mtls_cert_for_user(auth_client, user_a['id'], 'Deep Revoke Cert')
        cert_id = cert.get('id')

        # Monkeypatch _is_admin_or_operator and _is_auditor to return False
        # for user_b, simulating a custom role with write:user_certificates
        # but without operator/admin/auditor privileges.
        original_admin_op = uc_module._is_admin_or_operator
        original_auditor = uc_module._is_auditor

        def _patched_admin_op(user):
            if getattr(user, 'username', '') == 'idor_deep_revoke_b':
                return False
            return original_admin_op(user)

        def _patched_auditor(user):
            if getattr(user, 'username', '') == 'idor_deep_revoke_b':
                return False
            return original_auditor(user)

        monkeypatch.setattr(uc_module, '_is_admin_or_operator', _patched_admin_op)
        monkeypatch.setattr(uc_module, '_is_auditor', _patched_auditor)

        r = post_json(user_b_client, f'{BASE}/{cert_id}/revoke', {'reason': 'unspecified'})
        assert r.status_code == 404, \
            f'Custom role user should not revoke another user cert: {r.data}'

    def test_custom_role_can_revoke_own_cert(
        self, app, auth_client, create_user, monkeypatch, mtls_ca
    ):
        """A non-operator user with write:user_certificates can revoke their own cert."""
        from api.v2 import user_certificates as uc_module

        user_b_client, user_b = _create_user_and_login(
            app, auth_client, create_user, 'idor_deep_revoke_own'
        )
        cert = _create_mtls_cert_for_user(auth_client, user_b['id'], 'Deep Own Cert')
        cert_id = cert.get('id')

        original_admin_op = uc_module._is_admin_or_operator
        original_auditor = uc_module._is_auditor

        def _patched_admin_op(user):
            if getattr(user, 'username', '') == 'idor_deep_revoke_own':
                return False
            return original_admin_op(user)

        def _patched_auditor(user):
            if getattr(user, 'username', '') == 'idor_deep_revoke_own':
                return False
            return original_auditor(user)

        monkeypatch.setattr(uc_module, '_is_admin_or_operator', _patched_admin_op)
        monkeypatch.setattr(uc_module, '_is_auditor', _patched_auditor)

        r = post_json(user_b_client, f'{BASE}/{cert_id}/revoke', {'reason': 'unspecified'})
        assert r.status_code == 200, \
            f'Custom role user should revoke own cert: {r.data}'

    def test_custom_role_cannot_delete_other_user_cert(
        self, app, auth_client, create_user, monkeypatch, mtls_ca
    ):
        """A non-operator user with delete:user_certificates cannot delete another's cert."""
        from api.v2 import user_certificates as uc_module

        _, user_a = _create_user_and_login(
            app, auth_client, create_user, 'idor_deep_delete_a'
        )
        user_b_client, user_b = _create_user_and_login(
            app, auth_client, create_user, 'idor_deep_delete_b'
        )
        cert = _create_mtls_cert_for_user(auth_client, user_a['id'], 'Deep Delete Cert')
        cert_id = cert.get('id')

        original_admin_op = uc_module._is_admin_or_operator
        original_auditor = uc_module._is_auditor

        def _patched_admin_op(user):
            if getattr(user, 'username', '') == 'idor_deep_delete_b':
                return False
            return original_admin_op(user)

        def _patched_auditor(user):
            if getattr(user, 'username', '') == 'idor_deep_delete_b':
                return False
            return original_auditor(user)

        monkeypatch.setattr(uc_module, '_is_admin_or_operator', _patched_admin_op)
        monkeypatch.setattr(uc_module, '_is_auditor', _patched_auditor)

        r = user_b_client.delete(f'{BASE}/{cert_id}')
        assert r.status_code == 404, \
            f'Custom role user should not delete another user cert: {r.data}'

    def test_custom_role_can_delete_own_cert(
        self, app, auth_client, create_user, monkeypatch, mtls_ca
    ):
        """A non-operator user with delete:user_certificates can delete their own cert."""
        from api.v2 import user_certificates as uc_module

        user_b_client, user_b = _create_user_and_login(
            app, auth_client, create_user, 'idor_deep_delete_own'
        )
        cert = _create_mtls_cert_for_user(auth_client, user_b['id'], 'Deep Own Delete Cert')
        cert_id = cert.get('id')

        original_admin_op = uc_module._is_admin_or_operator
        original_auditor = uc_module._is_auditor

        def _patched_admin_op(user):
            if getattr(user, 'username', '') == 'idor_deep_delete_own':
                return False
            return original_admin_op(user)

        def _patched_auditor(user):
            if getattr(user, 'username', '') == 'idor_deep_delete_own':
                return False
            return original_auditor(user)

        monkeypatch.setattr(uc_module, '_is_admin_or_operator', _patched_admin_op)
        monkeypatch.setattr(uc_module, '_is_auditor', _patched_auditor)

        r = user_b_client.delete(f'{BASE}/{cert_id}')
        assert r.status_code == 204, \
            f'Custom role user should delete own cert: {r.data}'
