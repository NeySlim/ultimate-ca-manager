"""Every administration route refuses a role without the right, and does nothing.

The routes are enumerated from ``app.url_map``: every route of
``api.v2.system`` and every route outside it whose decorator requires an
``admin:*`` scope. Each one is written below with the scope decided for it, so
a new route without a line fails the suite, and a decorator that loses its
scope fails the grid: the role that should be refused is let in.

A probe never runs the route itself. The function behind ``require_auth`` is
swapped for a recorder, so a refusal is proven to stop before the view body
(nothing it does can have happened) and a grant is proven to reach it, without
ever rotating a key, resetting the database or installing an update.

Because the probe replaces the view body, a scope check made INSIDE a view
(for example in `api/v2/system/service.py`) is not covered by this grid.
"""
import contextlib
import json
import re

import pytest

from auth.permissions import CUSTOM_ROLE_GRANTABLE_PERMISSIONS
from auth.unified import require_auth
from models import db, User
from models.rbac import CustomRole
from models.user import UserSession

pytestmark = pytest.mark.usefixtures('drop_new_users')

ADMIN_SYSTEM = ('admin:system',)
ADMIN_SETTINGS = ('admin:settings',)
ADMIN_USERS = ('admin:users',)
ADMIN_KEY_RECOVERY = ('admin:key_recovery',)
READ_SETTINGS = ('read:settings',)
WRITE_SETTINGS = ('write:settings',)
READ_CAS = ('read:cas',)
WRITE_CAS = ('write:cas',)
SIGNED_IN = ()          # require_auth() with no scope
PUBLIC = None           # no require_auth at all

SYSTEM_PREFIX = 'api.v2.system'

# Every route this grid covers, with the scope its decorator must require.
ROUTES = {
    # api.v2.database
    'POST /api/v2/database/migrate': ADMIN_SETTINGS,
    'POST /api/v2/database/switch': ADMIN_SETTINGS,
    'POST /api/v2/database/test': ADMIN_SETTINGS,
    # api.v2.discovery
    'DELETE /api/v2/discovery': ADMIN_SYSTEM,
    'DELETE /api/v2/discovery/profiles/<int:profile_id>': ADMIN_SYSTEM,
    'POST /api/v2/discovery/bulk-resolve-dns': ADMIN_SYSTEM,
    'POST /api/v2/discovery/profiles': ADMIN_SYSTEM,
    'POST /api/v2/discovery/profiles/<int:profile_id>/scan': ADMIN_SYSTEM,
    'POST /api/v2/discovery/scan': ADMIN_SYSTEM,
    'PUT /api/v2/discovery/profiles/<int:profile_id>': ADMIN_SYSTEM,
    # api.v2.hsm
    'POST /api/v2/hsm/dependencies/install': ADMIN_SYSTEM,
    # api.v2.key_recovery
    'POST /api/v2/key-recovery/<int:rid>/approve': ADMIN_KEY_RECOVERY,
    'POST /api/v2/key-recovery/<int:rid>/reject': ADMIN_KEY_RECOVERY,
    # api.v2.msca
    'POST /api/v2/microsoft-cas/<int:msca_id>/admin-channel/test': ADMIN_SYSTEM,
    'POST /api/v2/microsoft-cas/<int:msca_id>/ca/pending/<int:request_id>/approve': ADMIN_SYSTEM,
    'POST /api/v2/microsoft-cas/<int:msca_id>/ca/pending/<int:request_id>/deny': ADMIN_SYSTEM,
    'POST /api/v2/microsoft-cas/<int:msca_id>/inventory-sync': ADMIN_SYSTEM,
    'POST /api/v2/microsoft-cas/<int:msca_id>/publish-crl': ADMIN_SYSTEM,
    # api.v2.mtls
    'PUT /api/v2/mtls/settings': ADMIN_SYSTEM,
    # api.v2.rbac
    'DELETE /api/v2/rbac/roles/<int:role_id>': ADMIN_USERS,
    'GET /api/v2/rbac/effective-permissions/<int:user_id>': ADMIN_USERS,
    'GET /api/v2/rbac/permissions': ADMIN_USERS,
    'POST /api/v2/rbac/roles': ADMIN_USERS,
    'PUT /api/v2/rbac/roles/<int:role_id>': ADMIN_USERS,
    # api.v2.settings.auto_renewal
    'POST /api/v2/settings/auto-renewal/run': ADMIN_SETTINGS,
    # api.v2.settings.backup
    'DELETE /api/v2/settings/backup/<filename>': ADMIN_SYSTEM,
    'GET /api/v2/settings/backup/<filename>/download': ADMIN_SYSTEM,
    'GET /api/v2/settings/backup/history': ADMIN_SYSTEM,
    'PATCH /api/v2/settings/backup/schedule': ADMIN_SYSTEM,
    'POST /api/v2/settings/backup/create': ADMIN_SYSTEM,
    'POST /api/v2/settings/backup/restore': ADMIN_SYSTEM,
    # api.v2.settings.general
    'PATCH /api/v2/settings/ct': ADMIN_SETTINGS,
    # api.v2.settings.notifications
    'GET /api/v2/settings/audit-logs': ADMIN_SYSTEM,
    # api.v2.system.alerts
    'GET /api/v2/system/alerts/expiry': READ_SETTINGS,
    'POST /api/v2/system/alerts/expiry/check': ADMIN_SYSTEM,
    'PUT /api/v2/system/alerts/expiry': ADMIN_SYSTEM,
    # api.v2.system.audit
    'GET /api/v2/system/audit/retention': READ_SETTINGS,
    'GET /api/v2/system/audit/syslog': READ_SETTINGS,
    'POST /api/v2/system/audit/cleanup': ADMIN_SYSTEM,
    'POST /api/v2/system/audit/syslog/test': ADMIN_SYSTEM,
    'PUT /api/v2/system/audit/retention': ADMIN_SYSTEM,
    'PUT /api/v2/system/audit/syslog': ADMIN_SYSTEM,
    # api.v2.system.backup
    'DELETE /api/v2/system/backup/<filename>': ADMIN_SYSTEM,
    'GET /api/v2/system/backup/<filename>/download': ADMIN_SYSTEM,
    'GET /api/v2/system/backup/list': ADMIN_SYSTEM,
    'GET /api/v2/system/backups': ADMIN_SYSTEM,
    'POST /api/v2/system/backup': ADMIN_SYSTEM,
    'POST /api/v2/system/backup/create': ADMIN_SYSTEM,
    'POST /api/v2/system/backup/restore': ADMIN_SYSTEM,
    'POST /api/v2/system/backups/bulk-delete': ADMIN_SYSTEM,
    'POST /api/v2/system/backups/run-retention': ADMIN_SYSTEM,
    'POST /api/v2/system/restore': ADMIN_SYSTEM,
    # api.v2.system.database
    'GET /api/v2/system/database/export': ADMIN_SYSTEM,
    'GET /api/v2/system/database/stats': READ_SETTINGS,
    'POST /api/v2/system/database/integrity-check': ADMIN_SYSTEM,
    'POST /api/v2/system/database/optimize': ADMIN_SYSTEM,
    'POST /api/v2/system/database/reset': ADMIN_SYSTEM,
    # api.v2.system.https
    'GET /api/v2/system/https/cert-info': READ_SETTINGS,
    'POST /api/v2/system/https/apply': ADMIN_SYSTEM,
    'POST /api/v2/system/https/regenerate': ADMIN_SYSTEM,
    'POST /api/v2/system/https/unbind': ADMIN_SYSTEM,
    # api.v2.system.jobs: each job's own permission, checked inline
    'GET /api/v2/system/jobs': SIGNED_IN,
    'GET /api/v2/system/jobs/<job_id>': SIGNED_IN,
    'POST /api/v2/system/jobs/<job_id>/cancel': SIGNED_IN,
    # api.v2.system.logs
    'GET /api/v2/system/logs': ADMIN_SYSTEM,
    'GET /api/v2/system/logs/bundle': ADMIN_SYSTEM,
    # api.v2.system.maintenance
    'DELETE /api/v2/system/maintenance': ADMIN_SYSTEM,
    'GET /api/v2/system/maintenance': ADMIN_SYSTEM,
    'POST /api/v2/system/maintenance': ADMIN_SYSTEM,
    # api.v2.system.security
    'GET /api/v2/system/security/anomalies': ADMIN_SYSTEM,
    'GET /api/v2/system/security/encryption-status': ADMIN_SYSTEM,
    'GET /api/v2/system/security/generate-key': ADMIN_SYSTEM,
    'GET /api/v2/system/security/master-key/download': ADMIN_SYSTEM,
    'GET /api/v2/system/security/rate-limit': READ_SETTINGS,
    'GET /api/v2/system/security/rate-limit/stats': READ_SETTINGS,
    'GET /api/v2/system/security/secrets-status': ADMIN_SYSTEM,
    'POST /api/v2/system/security/disable-encryption': ADMIN_SYSTEM,
    'POST /api/v2/system/security/enable-encryption': ADMIN_SYSTEM,
    'POST /api/v2/system/security/encrypt-all-keys': ADMIN_SYSTEM,
    'POST /api/v2/system/security/rate-limit/reset': ADMIN_SYSTEM,
    'POST /api/v2/system/security/rotate-encryption-key': ADMIN_SYSTEM,
    'POST /api/v2/system/security/rotate-secrets': ADMIN_SYSTEM,
    'PUT /api/v2/system/security/rate-limit': ADMIN_SYSTEM,
    # api.v2.system.service
    'GET /api/v2/system/chain-repair': READ_CAS,
    'GET /api/v2/system/compliance-preflight': ADMIN_SYSTEM,
    'GET /api/v2/system/compliance-profiles': SIGNED_IN,
    'GET /api/v2/system/fips-preflight': ADMIN_SYSTEM,
    'GET /api/v2/system/hsm-status': READ_SETTINGS,
    'GET /api/v2/system/scheduler': READ_SETTINGS,
    'GET /api/v2/system/service/status': READ_SETTINGS,
    'POST /api/v2/system/chain-repair/run': WRITE_CAS,
    'POST /api/v2/system/scheduler/<task_name>/run': ADMIN_SYSTEM,
    'POST /api/v2/system/service/restart': WRITE_SETTINGS,
    # api.v2.system.updates
    'GET /api/v2/system/updates/campaign': ADMIN_SYSTEM,
    'GET /api/v2/system/updates/check': ADMIN_SYSTEM,
    'GET /api/v2/system/updates/settings': ADMIN_SYSTEM,
    'GET /api/v2/system/updates/version': PUBLIC,
    'GET /api/v2/system/updates/whatsnew': SIGNED_IN,
    'PATCH /api/v2/system/updates/settings': ADMIN_SYSTEM,
    'POST /api/v2/system/updates/campaign/resume': ADMIN_SYSTEM,
    'POST /api/v2/system/updates/install': ADMIN_SYSTEM,
    # api.v2.users.mtls
    'DELETE /api/v2/users/<int:user_id>/mtls/certificates/<int:cert_id>': ADMIN_USERS,
    'GET /api/v2/users/<int:user_id>/mtls/certificates': ADMIN_USERS,
    'POST /api/v2/users/<int:user_id>/mtls/certificates': ADMIN_USERS,
    # api.v2.websocket
    'GET /api/v2/websocket/clients': ADMIN_SYSTEM,
    'POST /api/v2/websocket/broadcast': ADMIN_SYSTEM,
}

GRANTED = 'granted'
ROLES = ('admin', 'operator', 'auditor', 'viewer', 'custom')
_REFUSED_TO_ALL = {'admin': GRANTED, 'operator': 403, 'auditor': 403,
                   'viewer': 403, 'custom': 403}

# What each built-in role, and a custom role holding every scope a custom role
# may grant, must get from a route that requires this scope. Written by hand.
EXPECTED = {
    ADMIN_SYSTEM: _REFUSED_TO_ALL,
    ADMIN_SETTINGS: _REFUSED_TO_ALL,
    ADMIN_USERS: _REFUSED_TO_ALL,
    ADMIN_KEY_RECOVERY: _REFUSED_TO_ALL,
    READ_SETTINGS: {'admin': GRANTED, 'operator': GRANTED, 'auditor': 403,
                    'viewer': 403, 'custom': GRANTED},
    WRITE_SETTINGS: {'admin': GRANTED, 'operator': GRANTED, 'auditor': 403,
                     'viewer': 403, 'custom': GRANTED},
    READ_CAS: {role: GRANTED for role in ROLES},
    WRITE_CAS: {'admin': GRANTED, 'operator': GRANTED, 'auditor': 403,
                'viewer': 403, 'custom': GRANTED},
    SIGNED_IN: {role: GRANTED for role in ROLES},
    PUBLIC: {role: GRANTED for role in ROLES},
}

# Built without a scope: a scope named here would join ENFORCED_PERMISSIONS
_GATE_CODE = require_auth()(lambda: None).__code__
_PLACEHOLDER = re.compile(r'<(?:(\w+)(?:\([^)]*\))?:)?(\w+)>')
SENTINEL = {'matrix_probe': 'view reached'}


def _layers(view):
    while view is not None:
        yield view
        view = getattr(view, '__wrapped__', None)


def _gate(view):
    """The require_auth wrapper of a view, or None when the route has none."""
    for layer in _layers(view):
        if getattr(layer, '__code__', None) is _GATE_CODE:
            return layer
    return None


def _cell(gate, name):
    return gate.__closure__[gate.__code__.co_freevars.index(name)]


def _covered_routes(app):
    """(label -> (endpoint, scope)) for the routes this grid must decide."""
    found = {}
    for rule in app.url_map.iter_rules():
        view = app.view_functions.get(rule.endpoint)
        gate = _gate(view)
        scope = (PUBLIC if gate is None
                 else tuple(_cell(gate, 'permissions').cell_contents or ()))
        in_system = getattr(view, '__module__', '').startswith(SYSTEM_PREFIX)
        admin = any(p.startswith('admin:') for p in scope or ())
        if not (in_system or admin):
            continue
        for method in rule.methods - {'HEAD', 'OPTIONS'}:
            found[f'{method} {rule.rule}'] = (rule.endpoint, scope)
    return found


def _url(rule):
    return _PLACEHOLDER.sub(
        lambda m: '1' if m.group(1) in ('int', 'float') else 'matrix-probe', rule)


def _row_counts():
    return {table.name: db.session.execute(
        db.select(db.func.count()).select_from(table)).scalar()
        for table in db.metadata.sorted_tables}


@contextlib.contextmanager
def _recorded(app, endpoint):
    """Swap the view behind require_auth for a recorder; yields the call list."""
    gate = _gate(app.view_functions[endpoint])
    # Without a gate there is nothing to swap: fail before the real view runs
    if gate is None:
        pytest.fail(f'{endpoint} has no require_auth; the probe would run the view')
    calls = []
    cell = _cell(gate, 'f')
    original = cell.cell_contents

    def recorder(*args, **kwargs):
        calls.append((args, kwargs))
        return SENTINEL, 200

    cell.cell_contents = recorder
    try:
        yield calls
    finally:
        cell.cell_contents = original


def _send(client, method, rule):
    body = {} if method in ('POST', 'PUT', 'PATCH') else None
    kwargs = {'data': json.dumps(body), 'content_type': 'application/json'} if body is not None else {}
    return client.open(_url(rule), method=method, **kwargs)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def _login(app, username):
    client = app.test_client()
    response = client.post('/api/v2/auth/login',
                           data=json.dumps({'username': username,
                                            'password': 'TestPass123!'}),
                           content_type='application/json')
    assert response.status_code == 200, response.data
    return client


@pytest.fixture(scope='module')
def clients(app, auth_client, create_user):
    """One signed-in client per role, the custom role on top of a viewer."""
    names = {role: f'matrix_admin_{role}' for role in ROLES if role != 'admin'}
    for role in ('operator', 'auditor', 'viewer'):
        create_user(username=names[role], role=role)
    create_user(username=names['custom'], role='viewer')

    response = auth_client.post('/api/v2/rbac/roles', data=json.dumps({
        'name': 'matrix-admin-everything-grantable',
        'permissions': list(CUSTOM_ROLE_GRANTABLE_PERMISSIONS)}),
        content_type='application/json')
    assert response.status_code == 200, response.data
    role_id = response.get_json()['data']['id']
    with app.app_context():
        custom_id = User.query.filter_by(username=names['custom']).one().id
    response = auth_client.put(f'/api/v2/users/{custom_id}',
                               data=json.dumps({'custom_role_id': role_id}),
                               content_type='application/json')
    assert response.status_code == 200, response.data

    signed_in = {role: _login(app, name) for role, name in names.items()}
    signed_in['admin'] = auth_client
    yield signed_in

    with app.app_context():
        ids = [u.id for u in User.query.filter(User.username.in_(names.values()))]
        UserSession.query.filter(UserSession.user_id.in_(ids)).delete(
            synchronize_session=False)
        User.query.filter(User.id.in_(ids)).update(
            {'custom_role_id': None}, synchronize_session=False)
        CustomRole.query.filter_by(id=role_id).delete(synchronize_session=False)
        db.session.commit()


# ---------------------------------------------------------------------------
# The table is the whole list
# ---------------------------------------------------------------------------

class TestEveryAdministrationRouteHasADecidedScope:
    def test_the_inventory_finds_the_routes_at_all(self, app):
        assert len(_covered_routes(app)) >= 100

    def test_no_route_is_missing_from_the_grid(self, app):
        missing = sorted(set(_covered_routes(app)) - set(ROUTES))
        assert not missing, (
            'these routes are not in the administration grid; add them with '
            f'the scope decided for them: {missing}')

    def test_every_decorator_requires_the_scope_decided_for_it(self, app):
        found = {label: scope for label, (_e, scope) in _covered_routes(app).items()}
        wrong = {label: (found[label], ROUTES[label])
                 for label in sorted(set(found) & set(ROUTES))
                 if found[label] != ROUTES[label]}
        assert not wrong, f'decorator scope differs from the grid (found, decided): {wrong}'

    def test_the_grid_holds_no_route_that_is_gone_or_lost_its_scope(self, app):
        stale = sorted(set(ROUTES) - set(_covered_routes(app)))
        assert not stale, f'the grid describes routes that are not there: {stale}'

    def test_every_scope_has_a_decided_row(self):
        for label, scope in ROUTES.items():
            assert scope in EXPECTED, label
            assert set(EXPECTED[scope]) == set(ROLES), label

    def test_a_custom_role_cannot_hold_an_admin_scope(self):
        """The `custom` column stands for the most a custom role may be given."""
        assert not [p for p in CUSTOM_ROLE_GRANTABLE_PERMISSIONS
                    if p.startswith('admin:') or '*' in p]


# ---------------------------------------------------------------------------
# The grid itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('label', sorted(ROUTES))
@pytest.mark.parametrize('role', ROLES)
def test_route_by_role(app, clients, label, role):
    method, rule = label.split(' ', 1)
    expected = EXPECTED[ROUTES[label]][role]
    endpoint, _scope = _covered_routes(app)[label]

    if ROUTES[label] is PUBLIC:
        response = _send(clients[role], method, rule)
        assert response.status_code == 200, (role, label, response.data[:300])
        return

    with app.app_context():
        before = _row_counts()
    with _recorded(app, endpoint) as calls:
        response = _send(clients[role], method, rule)

    if expected is GRANTED:
        assert calls and response.get_json() == SENTINEL, (
            f'{role} holds the right for {label} but got '
            f'{response.status_code}: {response.data[:300]}')
        return

    assert response.status_code == expected, (
        f'{role} must be refused {label} with {expected}, got '
        f'{response.status_code}: {response.data[:300]}')
    assert not calls, f'{role} reached the view of {label}'
    assert response.get_json()['message'] == 'Insufficient permissions'
    with app.app_context():
        assert _row_counts() == before, f'refusing {role} on {label} changed the database'


@pytest.mark.parametrize('label', sorted(
    label for label, scope in ROUTES.items() if scope is not PUBLIC))
def test_no_session_is_refused_before_any_scope(app, client, label):
    method, rule = label.split(' ', 1)
    endpoint, _scope = _covered_routes(app)[label]
    with _recorded(app, endpoint) as calls:
        response = _send(client, method, rule)
    assert response.status_code == 401, (label, response.data[:300])
    assert not calls
