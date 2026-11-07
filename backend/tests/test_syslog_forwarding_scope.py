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


def _entry(resource_type):
    log = Mock()
    log.timestamp = None
    log.action, log.username, log.ip_address = f'probe_{resource_type}', 'tester', None
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
        assert syslog_forwarder.send(_entry('sso'))
    forwarding(categories=['certificate'])
    with app.app_context():
        assert not syslog_forwarder.send(_entry('sso'))


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
