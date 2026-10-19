"""An administrator lists, disables and removes another user's security keys.

A lost key otherwise keeps signing its finder in without a password. The
routes are for administrators only, keep the last factor of required 2FA
unless the removal is confirmed, and audit who acted on which key of whom.
"""
import pytest

from auth import permissions
from models import User, db
from models.audit_log import AuditLog
from models.group import Group, GroupMember
from models.rbac import CustomRole
from models.webauthn import WebAuthnCredential
from tests.conftest import get_json
from tests.test_2fa_security_key_enforcement import _key_ids
from tests.test_webauthn_second_factor import enforce_2fa, make_user, _password  # noqa: F401 (fixtures)
from tests.test_webauthn_second_factor_optin import _flag, _password_session


def _uid(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).first().id


def _url(app, username, key_id=None):
    base = f'/api/v2/users/{_uid(app, username)}/webauthn'
    return base if key_id is None else f'{base}/{key_id}'


def _patch(c, url, enabled):
    return c.patch(url, json={'enabled': enabled})


def test_admin_lists_and_removes_a_lost_key(app, auth_client, make_user, enforce_2fa):
    username, _key, _ = make_user()
    key_id, = _key_ids(app, username)
    listed = get_json(auth_client.get(_url(app, username)))['data']
    assert [k['id'] for k in listed] == [key_id]
    assert auth_client.delete(_url(app, username, key_id)).status_code == 200
    assert _key_ids(app, username) == []
    with app.app_context():
        entry = AuditLog.query.filter_by(action='webauthn_admin_delete').order_by(AuditLog.id.desc()).first()
        assert entry.username == 'admin' and entry.resource_name == username
        assert f'(id {key_id})' in entry.details and '"soft"' in entry.details


def test_admin_disables_then_enables_a_key(app, auth_client, make_user):
    username, _key, _ = make_user()
    key_id, = _key_ids(app, username)
    assert _patch(auth_client, _url(app, username, key_id), False).status_code == 200
    with app.app_context():
        assert db.session.get(WebAuthnCredential, key_id).enabled is False
        assert AuditLog.query.filter_by(action='webauthn_admin_disable', resource_name=username).count() == 1
    assert _patch(auth_client, _url(app, username, key_id), True).status_code == 200
    with app.app_context():
        assert db.session.get(WebAuthnCredential, key_id).enabled is True


def test_enabled_must_be_boolean(app, auth_client, make_user):
    username, _key, _ = make_user()
    key_id, = _key_ids(app, username)
    assert auth_client.patch(_url(app, username, key_id), json={'enabled': 'no'}).status_code == 400


def test_key_of_another_account_is_not_found(app, auth_client, make_user):
    owner, _k, _ = make_user()
    other, _n, _ = make_user(key=False)
    key_id, = _key_ids(app, owner)
    assert auth_client.delete(_url(app, other, key_id)).status_code == 404
    assert _key_ids(app, owner) == [key_id]


def test_last_factor_needs_a_confirmation(app, auth_client, make_user, enforce_2fa):
    username, _key, _ = make_user(totp=False)
    key_id, = _key_ids(app, username)
    r = auth_client.delete(_url(app, username, key_id))
    assert r.status_code == 409
    assert _patch(auth_client, _url(app, username, key_id), False).status_code == 409
    assert _key_ids(app, username) == [key_id]

    assert auth_client.delete(_url(app, username, key_id) + '?confirm=last_factor').status_code == 200
    assert _key_ids(app, username) == []
    assert _flag(app, username) is False
    assert get_json(_password(app.test_client(), username))['data'].get('requires_2fa_enrollment') is True


def test_a_disabled_key_goes_without_confirmation(app, auth_client, make_user, enforce_2fa):
    username, _key, _ = make_user(totp=False)
    key_id, = _key_ids(app, username)
    assert _patch(auth_client, _url(app, username, key_id) + '?confirm=last_factor', False).status_code == 200
    assert auth_client.delete(_url(app, username, key_id)).status_code == 200


def test_last_factor_without_enforcement_goes_freely(app, auth_client, make_user):
    username, _key, _ = make_user(totp=False)
    key_id, = _key_ids(app, username)
    assert auth_client.delete(_url(app, username, key_id)).status_code == 200


def test_a_non_admin_is_refused(app, make_user):
    target, _k, _ = make_user()
    key_id, = _key_ids(app, target)
    operator, _n, _ = make_user(totp=False, key=False)
    c = _password_session(app, operator)
    assert c.get(_url(app, target)).status_code == 403
    assert c.delete(_url(app, target, key_id)).status_code == 403
    assert _patch(c, _url(app, target, key_id), False).status_code == 403
    assert _key_ids(app, target) == [key_id]


@pytest.fixture
def granted_everything(app, make_user):
    """An operator holding every permission a group or a custom role may grant."""
    grantable = sorted(getattr(permissions, 'CUSTOM_ROLE_GRANTABLE_PERMISSIONS',
                               permissions.GROUP_GRANTABLE_PERMISSIONS))
    username, _n, _ = make_user(totp=False, key=False)
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        role = CustomRole(name=f'all-grantable-{username}', permissions=grantable)
        group = Group(name=f'all-grantable-{username}', description='',
                      permissions=list(permissions.GROUP_GRANTABLE_PERMISSIONS))
        db.session.add_all([role, group])
        db.session.flush()
        user.custom_role_id = role.id
        db.session.add(GroupMember(group_id=group.id, user_id=user.id))
        db.session.commit()
        ids = (role.id, group.id)
    yield username
    with app.app_context():
        GroupMember.query.filter_by(group_id=ids[1]).delete()
        User.query.filter_by(username=username).update({'custom_role_id': None})
        db.session.delete(db.session.get(Group, ids[1]))
        db.session.delete(db.session.get(CustomRole, ids[0]))
        db.session.commit()


def test_grantable_permissions_are_not_enough(app, make_user, granted_everything):
    target, _k, _ = make_user()
    key_id, = _key_ids(app, target)
    c = _password_session(app, granted_everything)
    assert c.get(_url(app, target)).status_code == 403
    assert c.delete(_url(app, target, key_id)).status_code == 403
    assert _key_ids(app, target) == [key_id]


def test_owner_route_no_longer_reaches_other_keys(app, auth_client, make_user):
    username, _key, _ = make_user()
    key_id, = _key_ids(app, username)
    assert auth_client.delete(f'/api/v2/webauthn/credentials/{key_id}').status_code == 404
    assert _key_ids(app, username) == [key_id]
