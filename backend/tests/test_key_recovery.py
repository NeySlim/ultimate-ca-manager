"""Tests for the dual-control key recovery (escrow) workflow."""
import json
import pytest

from models import db, SystemConfig, KeyRecoveryRequest


def _set_dual_control(app, enabled):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='key_recovery_dual_control').first()
        if not row:
            row = SystemConfig(key='key_recovery_dual_control', value='')
            db.session.add(row)
        row.value = 'true' if enabled else 'false'
        db.session.commit()


@pytest.fixture
def archived_cert(app, create_cert):
    info = create_cert(cn='escrow-test.example.com', validity_days=365)
    return info['id']


class TestRequest:
    def test_requires_auth(self, client, archived_cert):
        r = client.post(f'/api/v2/certificates/{archived_cert}/key-recovery',
                        data=json.dumps({'reason': 'x'}), content_type='application/json')
        assert r.status_code == 401

    def test_reason_required(self, auth_client, archived_cert):
        r = auth_client.post(f'/api/v2/certificates/{archived_cert}/key-recovery',
                             data=json.dumps({}), content_type='application/json')
        assert r.status_code == 400

    def test_unknown_cert_404(self, auth_client):
        r = auth_client.post('/api/v2/certificates/999999/key-recovery',
                             data=json.dumps({'reason': 'lost laptop'}), content_type='application/json')
        assert r.status_code == 404

    def test_creates_pending(self, auth_client, archived_cert):
        r = auth_client.post(f'/api/v2/certificates/{archived_cert}/key-recovery',
                             data=json.dumps({'reason': 'employee offboarding'}),
                             content_type='application/json')
        assert r.status_code == 201
        body = json.loads(r.data)['data']
        assert body['status'] == 'pending'
        assert body['cert_id'] == archived_cert
        assert body['requested_by']


def _open_request(auth_client, cert_id, reason='offboarding'):
    r = auth_client.post(f'/api/v2/certificates/{cert_id}/key-recovery',
                         data=json.dumps({'reason': reason}), content_type='application/json')
    return json.loads(r.data)['data']['id']


class TestDualControl:
    def test_requester_cannot_approve_own(self, app, auth_client, archived_cert):
        _set_dual_control(app, True)
        rid = _open_request(auth_client, archived_cert)
        r = auth_client.post(f'/api/v2/key-recovery/{rid}/approve',
                             data=json.dumps({}), content_type='application/json')
        assert r.status_code == 403  # admin requested AND tried to approve

    def test_self_approve_when_dual_control_off(self, app, auth_client, archived_cert):
        _set_dual_control(app, False)
        rid = _open_request(auth_client, archived_cert)
        r = auth_client.post(f'/api/v2/key-recovery/{rid}/approve',
                             data=json.dumps({'note': 'ok'}), content_type='application/json')
        assert r.status_code == 200
        assert json.loads(r.data)['data']['status'] == 'approved'


class TestRecover:
    def test_full_flow_returns_pkcs12(self, app, auth_client, archived_cert):
        _set_dual_control(app, False)
        rid = _open_request(auth_client, archived_cert)
        auth_client.post(f'/api/v2/key-recovery/{rid}/approve',
                         data=json.dumps({}), content_type='application/json')
        r = auth_client.post(f'/api/v2/key-recovery/{rid}/recover',
                             data=json.dumps({'password': 'recover-pw-123'}),
                             content_type='application/json')
        assert r.status_code == 200
        assert r.headers['Content-Type'] == 'application/x-pkcs12'
        assert r.data[:1] == b'\x30'  # DER SEQUENCE — a PKCS12 blob
        with app.app_context():
            assert KeyRecoveryRequest.query.get(rid).status == 'recovered'

    def test_cannot_recover_before_approval(self, app, auth_client, archived_cert):
        _set_dual_control(app, False)
        rid = _open_request(auth_client, archived_cert)
        r = auth_client.post(f'/api/v2/key-recovery/{rid}/recover',
                             data=json.dumps({'password': 'recover-pw-123'}),
                             content_type='application/json')
        assert r.status_code == 409  # not approved

    def test_recover_requires_password(self, app, auth_client, archived_cert):
        _set_dual_control(app, False)
        rid = _open_request(auth_client, archived_cert)
        auth_client.post(f'/api/v2/key-recovery/{rid}/approve',
                         data=json.dumps({}), content_type='application/json')
        r = auth_client.post(f'/api/v2/key-recovery/{rid}/recover',
                             data=json.dumps({'password': 'short'}), content_type='application/json')
        assert r.status_code == 400

    def test_cannot_recover_twice(self, app, auth_client, archived_cert):
        _set_dual_control(app, False)
        rid = _open_request(auth_client, archived_cert)
        auth_client.post(f'/api/v2/key-recovery/{rid}/approve',
                         data=json.dumps({}), content_type='application/json')
        ok = auth_client.post(f'/api/v2/key-recovery/{rid}/recover',
                              data=json.dumps({'password': 'recover-pw-123'}), content_type='application/json')
        assert ok.status_code == 200
        again = auth_client.post(f'/api/v2/key-recovery/{rid}/recover',
                                 data=json.dumps({'password': 'recover-pw-123'}), content_type='application/json')
        assert again.status_code == 409  # already recovered


class TestReject:
    def test_reject(self, app, auth_client, archived_cert):
        rid = _open_request(auth_client, archived_cert)
        r = auth_client.post(f'/api/v2/key-recovery/{rid}/reject',
                             data=json.dumps({'note': 'not justified'}), content_type='application/json')
        assert r.status_code == 200
        assert json.loads(r.data)['data']['status'] == 'rejected'


class TestList:
    def test_list_requires_auth(self, client):
        assert client.get('/api/v2/key-recovery').status_code == 401

    def test_list(self, auth_client, archived_cert):
        _open_request(auth_client, archived_cert)
        r = auth_client.get('/api/v2/key-recovery')
        assert r.status_code == 200
        body = json.loads(r.data)['data']
        assert 'requests' in body and 'dual_control' in body


class TestDualControlEnvOverride:
    """#137: KEY_RECOVERY_DUAL_CONTROL in the env overrides the DB row."""

    def test_env_false_overrides_db_on(self, app, monkeypatch):
        from api.v2.key_recovery import _dual_control_enabled
        _set_dual_control(app, True)  # DB says ON
        monkeypatch.setenv('KEY_RECOVERY_DUAL_CONTROL', 'false')
        with app.app_context():
            assert _dual_control_enabled() is False

    def test_env_lowercase_key_accepted(self, app, monkeypatch):
        from api.v2.key_recovery import _dual_control_enabled
        _set_dual_control(app, True)
        monkeypatch.delenv('KEY_RECOVERY_DUAL_CONTROL', raising=False)
        monkeypatch.setenv('key_recovery_dual_control', 'no')
        with app.app_context():
            assert _dual_control_enabled() is False

    def test_db_used_when_env_absent(self, app, monkeypatch):
        from api.v2.key_recovery import _dual_control_enabled
        monkeypatch.delenv('KEY_RECOVERY_DUAL_CONTROL', raising=False)
        monkeypatch.delenv('key_recovery_dual_control', raising=False)
        _set_dual_control(app, False)
        with app.app_context():
            assert _dual_control_enabled() is False
        _set_dual_control(app, True)
        with app.app_context():
            assert _dual_control_enabled() is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
