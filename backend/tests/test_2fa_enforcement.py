"""End-to-end tests for 2FA enforcement (#141).

Covers: initial-admin exemption, forced enrolment for local accounts when the
global toggle is ON, the require_auth gate during enrolment, promotion to a full
session after confirming TOTP, and the self-disable block under enforcement.
"""
import json
import pyotp

from tests.conftest import get_json


def _login(client, username, password):
    return client.post(
        '/api/v2/auth/login',
        data=json.dumps({'username': username, 'password': password}),
        content_type='application/json',
    )


def _set_global_enforce(admin_client, value):
    return admin_client.patch(
        '/api/v2/settings/general',
        data=json.dumps({'enforce_2fa': value}),
        content_type='application/json',
    )


def test_initial_admin_is_exempt(app, auth_client):
    """The bootstrap admin must be totp_exempt so it can never be locked out."""
    users = get_json(auth_client.get('/api/v2/users'))['data']
    admin = next(u for u in users if u['username'] == 'admin')
    assert admin['totp_exempt'] is True


def test_2fa_enforcement_end_to_end(app):
    admin = app.test_client()
    assert _login(admin, 'admin', 'changeme123').status_code == 200

    # A fresh local user without 2FA.
    admin.post(
        '/api/v2/users',
        data=json.dumps({
            'username': 'enf_user', 'password': 'EnfPass123!',
            'email': 'enf@test.local', 'role': 'operator',
        }),
        content_type='application/json',
    )

    try:
        assert _set_global_enforce(admin, True).status_code == 200

        # Login → forced into enrolment, not a full session.
        c = app.test_client()
        r = _login(c, 'enf_user', 'EnfPass123!')
        assert r.status_code == 200
        assert get_json(r)['data'].get('requires_2fa_enrollment') is True

        # Gate: any protected endpoint is blocked until TOTP is confirmed
        # (use /account/profile — reachable by any authenticated user, so this
        # isolates the enrolment gate from RBAC permission checks).
        r = c.get('/api/v2/account/profile')
        assert r.status_code == 403
        assert get_json(r).get('must_enroll_2fa') is True

        # verify() advertises the enrolment state for the frontend router.
        assert get_json(c.get('/api/v2/auth/verify'))['data'].get('must_enroll_2fa') is True

        # Enrol: enable → confirm.
        secret = get_json(c.post('/api/v2/account/2fa/enable', data='{}',
                                 content_type='application/json'))['data']['secret']
        r = c.post('/api/v2/account/2fa/confirm',
                   data=json.dumps({'code': pyotp.TOTP(secret).now()}),
                   content_type='application/json')
        assert r.status_code == 200

        # Session promoted: protected endpoint now reachable.
        assert c.get('/api/v2/account/profile').status_code == 200

        # Self-disable is blocked while enforcement is active.
        r = c.post('/api/v2/account/2fa/disable',
                   data=json.dumps({'code': pyotp.TOTP(secret).now()}),
                   content_type='application/json')
        assert r.status_code == 403

        # The exempt admin logs in normally even with enforcement ON.
        a2 = app.test_client()
        r = _login(a2, 'admin', 'changeme123')
        assert r.status_code == 200
        assert not get_json(r)['data'].get('requires_2fa_enrollment')
        assert a2.get('/api/v2/account/profile').status_code == 200
    finally:
        _set_global_enforce(admin, False)


def test_admin_can_reset_user_2fa(app):
    """Admin break-glass: reset a user's 2FA."""
    admin = app.test_client()
    assert _login(admin, 'admin', 'changeme123').status_code == 200

    users = get_json(admin.get('/api/v2/users'))['data']
    target = next(u for u in users if u['username'] == 'enf_user')

    r = admin.post(f"/api/v2/users/{target['id']}/reset-2fa", data='{}',
                   content_type='application/json')
    assert r.status_code == 200

    users = get_json(admin.get('/api/v2/users'))['data']
    target = next(u for u in users if u['username'] == 'enf_user')
    assert target['two_factor_enabled'] is False
