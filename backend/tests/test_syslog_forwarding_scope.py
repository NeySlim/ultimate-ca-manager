"""Remote syslog forwards every audit event the operator did not deselect,
including the ones written inside a caller's transaction (the audit purge)."""
import json
import socket
import uuid

import pytest
from unittest.mock import Mock

from services.syslog_service import SyslogForwarder, syslog_forwarder


@pytest.fixture
def collector():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1', 0))
    sock.settimeout(0.3)
    yield sock
    sock.close()


def _received(sock):
    packets = []
    while True:
        try:
            packets.append(sock.recv(65535).decode())
        except socket.timeout:
            return packets


@pytest.fixture
def forwarding(collector):
    """The singleton forwarder pointed at the collector, restored afterwards."""
    saved = dict(syslog_forwarder.__dict__)

    def configure(categories=None):
        syslog_forwarder.configure(enabled=True, host='127.0.0.1', port=collector.getsockname()[1],
                                   protocol='udp', categories=categories)
    configure()
    yield configure
    syslog_forwarder._close()
    syslog_forwarder.__dict__.clear()
    syslog_forwarder.__dict__.update(saved)
    syslog_forwarder._socket = None


def _entry(resource_type, action=None):
    log = Mock()
    log.timestamp = None
    log.action, log.username, log.ip_address = action or f'probe_{resource_type}', 'tester', None
    log.resource_type, log.resource_id, log.resource_name = resource_type, None, None
    log.success, log.details = True, 'probe'
    return log


ALL_TYPES = ['certificate', 'audit_log', 'api_key', 'rbac_role', 'settings', 'sso', 'acme_order',
             'acme_account', 'policy', 'security', 'key_recovery', 'hsm_key', None]


def test_default_categories_forward_every_resource_type(app, collector, forwarding):
    with app.app_context():
        for rtype in ALL_TYPES:
            assert syslog_forwarder.send(_entry(rtype)) is True, rtype
    assert len(_received(collector)) == len(ALL_TYPES)


def test_acme_box_covers_every_acme_type(app, collector, forwarding):
    forwarding(categories=['acme'])
    with app.app_context():
        assert syslog_forwarder.send(_entry('acme_order'))
        assert syslog_forwarder.send(_entry('acme_eab_credential'))
        assert not syslog_forwarder.send(_entry('certificate'))
    forwarding(categories=['certificate'])
    with app.app_context():
        assert not syslog_forwarder.send(_entry('acme_order'))


def test_sso_login_failures_follow_the_users_box(app, collector, forwarding):
    forwarding(categories=['user'])
    with app.app_context():
        assert syslog_forwarder.send(_entry('sso', 'login_failure'))
    forwarding(categories=['certificate'])
    with app.app_context():
        assert not syslog_forwarder.send(_entry('sso', 'login_failure'))
        assert not syslog_forwarder.send(_entry('user', 'logout'))


def test_account_changes_ignore_the_users_box(app, collector, forwarding):
    forwarding(categories=['certificate'])
    with app.app_context():
        for action in ('user_update', 'user_create', 'role_change', 'password_change',
                       'password_reset', 'mfa_disable', 'mfa_reset', 'user_activate'):
            assert syslog_forwarder.send(_entry('user', action)), action


def test_types_outside_the_boxes_are_never_dropped(app, collector, forwarding):
    forwarding(categories=['certificate'])
    with app.app_context():
        for rtype in ('audit_log', 'api_key', 'rbac_role', 'settings', 'policy'):
            assert syslog_forwarder.send(_entry(rtype)), rtype


def test_no_box_checked_is_read_back_as_all(app):
    from models import SystemConfig, db
    fwd = SyslogForwarder()
    saved = dict(fwd.__dict__)
    try:
        with app.app_context():
            row = SystemConfig.query.filter_by(key='syslog_categories').first()
            previous = row.value if row else None
            if row is None:
                row = SystemConfig(key='syslog_categories', value='')
                db.session.add(row)
            row.value = ''
            db.session.commit()
            try:
                fwd.load_from_db()
                fwd._enabled, fwd._host = True, '127.0.0.1'
                assert fwd._wanted('rbac_role') and fwd._wanted('certificate')
            finally:
                if previous is None:
                    db.session.delete(row)
                else:
                    row.value = previous
                db.session.commit()
    finally:
        fwd._close()
        fwd.__dict__.clear()
        fwd.__dict__.update(saved)


def test_syslog_forwards_role_creation_on_the_real_route(app, auth_client, collector, forwarding):
    name = f'syslog-{uuid.uuid4().hex[:8]}'
    r = auth_client.post('/api/v2/rbac/roles', content_type='application/json',
                         data=json.dumps({'name': name, 'permissions': ['read:certificates']}))
    assert r.status_code in (200, 201), r.get_json()
    packets = _received(collector)
    assert any(name in p and 'rbac_role' in p for p in packets), packets
    from models import db
    from models.rbac import CustomRole
    with app.app_context():
        CustomRole.query.filter_by(name=name).delete()
        db.session.commit()


def test_syslog_forwards_audit_cleanup_and_api_key_events(app, auth_client, collector, forwarding):
    from tests.test_audit_retention_cleanup import _row
    from models import AuditLog, db
    with app.app_context():
        AuditLog.query.filter(AuditLog.id < 0).delete(synchronize_session=False)
        db.session.commit()
        _row(-1, 4000)
    try:
        r = auth_client.post('/api/v2/audit/cleanup', content_type='application/json',
                             data=json.dumps({'retention_days': 3650}))
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['data']['deleted'] >= 1
        packets = _received(collector)
        assert any('audit_cleanup' in p and 'audit_log' in p for p in packets), packets

        r = auth_client.post('/api/v2/account/apikeys', content_type='application/json',
                             data=json.dumps({'name': 'syslog-probe', 'permissions': ['read:certificates']}))
        assert r.status_code in (200, 201), r.get_json()
        packets = _received(collector)
        assert any('api_key' in p for p in packets), packets
    finally:
        with app.app_context():
            AuditLog.query.filter(AuditLog.id < 0).delete(synchronize_session=False)
            from models.api_key import APIKey
            APIKey.query.filter_by(name='syslog-probe').delete()
            db.session.commit()


@pytest.fixture
def saved_syslog_rows(app):
    """The syslog_* settings the PUT route writes, restored afterwards."""
    from models import SystemConfig, db
    with app.app_context():
        rows = {r.key: r.value for r in SystemConfig.query.filter(SystemConfig.key.like('syslog_%'))}
    yield
    with app.app_context():
        for row in SystemConfig.query.filter(SystemConfig.key.like('syslog_%')):
            if row.key in rows:
                row.value = rows[row.key]
            else:
                db.session.delete(row)
        db.session.commit()


def _put_syslog(auth_client, collector, **fields):
    body = {'enabled': True, 'host': '127.0.0.1', 'port': collector.getsockname()[1],
            'protocol': 'udp', **fields}
    return auth_client.put('/api/v2/system/audit/syslog', content_type='application/json',
                           data=json.dumps(body))


def test_narrowing_the_categories_reaches_the_collector(app, auth_client, create_user, collector,
                                                         forwarding, saved_syslog_rows):
    r = _put_syslog(auth_client, collector, categories=['certificate', 'ca', 'csr', 'acme', 'scep'])
    assert r.status_code == 200, r.get_json()
    packets = [p for p in _received(collector) if 'syslog_config_updated' in p]
    assert len(packets) == 1, packets
    assert 'resource_type="settings"' in packets[0]
    assert 'system' in packets[0] and 'user' in packets[0], packets[0]

    user = create_user(username=f'sl-{uuid.uuid4().hex[:8]}')
    r = auth_client.put(f"/api/v2/users/{user['id']}", content_type='application/json',
                        data=json.dumps({'role': 'admin'}))
    assert r.status_code == 200, r.get_json()
    assert any('user_update' in p for p in _received(collector))


def test_disabling_forwarding_is_the_last_packet_sent(app, auth_client, collector, forwarding,
                                                       saved_syslog_rows):
    r = _put_syslog(auth_client, collector, enabled=False)
    assert r.status_code == 200, r.get_json()
    packets = [p for p in _received(collector) if 'syslog_config_updated' in p]
    assert len(packets) == 1 and 'disabled' in packets[0], packets


def test_no_box_checked_is_saved_and_shown_as_all(app, auth_client, collector, forwarding,
                                                   saved_syslog_rows):
    r = _put_syslog(auth_client, collector, categories=[])
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['categories'] == SyslogForwarder.ALL_CATEGORIES


def test_security_system_events_ignore_the_system_box(app, collector, forwarding):
    forwarding(categories=[c for c in SyslogForwarder.ALL_CATEGORIES if c != 'system'])
    from services.audit import AuditService
    actions = ('master_key_downloaded', 'encryption_disabled', 'system_restore', 'database_reset',
               'settings_update')
    with app.app_context():
        for action in actions:
            AuditService.log_action(action=action, resource_type='system', details='probe')
        assert not syslog_forwarder.send(_entry('system', 'system_optimize'))
    packets = _received(collector)
    for action in actions:
        assert any(action in p for p in packets), (action, packets)


def test_a_new_collector_receives_its_own_setup(app, auth_client, collector, forwarding,
                                                 saved_syslog_rows):
    syslog_forwarder.configure(enabled=False, host='', port=514, protocol='udp')
    r = _put_syslog(auth_client, collector)
    assert r.status_code == 200, r.get_json()
    packets = [p for p in _received(collector) if 'syslog_config_updated' in p]
    assert len(packets) == 1 and 'enabled' in packets[0], packets
    r = _put_syslog(auth_client, collector, categories=['certificate', 'ca'])
    assert r.status_code == 200, r.get_json()
    assert len([p for p in _received(collector) if 'syslog_config_updated' in p]) == 1
