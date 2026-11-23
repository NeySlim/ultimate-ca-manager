"""Tests for the Windows settings API's restart-on-WSTEP-toggle behavior.

gunicorn_config.py reads wstep_enabled once at worker startup to decide
whether the whole server needs the TLS-1.2-only cap some Windows
WSTEP/CEP clients require. That only stays correct if toggling the
setting actually restarts the service -- these tests check the signal
file restart_service() writes, not a real process restart.
"""
from pathlib import Path

from models import SystemConfig, db


def _set_config(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


def _restart_signal_path(app):
    from config.settings import DATA_DIR
    return Path(DATA_DIR) / '.restart_requested'


def _clear_restart_signal(app):
    with app.app_context():
        p = _restart_signal_path(app)
        if p.exists():
            p.unlink()


def test_enabling_wstep_triggers_restart(client, app, auth_client):
    with app.app_context():
        _set_config('wstep_enabled', 'false')
    _clear_restart_signal(app)

    r = auth_client.patch('/api/v2/windows-profiles/settings', json={'wstep_enabled': True})
    assert r.status_code == 200
    assert 'restarting' in r.get_json()['message'].lower()

    with app.app_context():
        assert _restart_signal_path(app).exists()

    _clear_restart_signal(app)
    with app.app_context():
        _set_config('wstep_enabled', 'false')


def test_disabling_wstep_triggers_restart(client, app, auth_client):
    with app.app_context():
        _set_config('wstep_enabled', 'true')
    _clear_restart_signal(app)

    r = auth_client.patch('/api/v2/windows-profiles/settings', json={'wstep_enabled': False})
    assert r.status_code == 200
    assert 'restarting' in r.get_json()['message'].lower()

    with app.app_context():
        assert _restart_signal_path(app).exists()

    _clear_restart_signal(app)


def test_setting_enabled_to_same_value_does_not_restart(client, app, auth_client):
    with app.app_context():
        _set_config('wstep_enabled', 'true')
    _clear_restart_signal(app)

    r = auth_client.patch('/api/v2/windows-profiles/settings', json={'wstep_enabled': True})
    assert r.status_code == 200
    assert 'restarting' not in r.get_json()['message'].lower()

    with app.app_context():
        assert not _restart_signal_path(app).exists()

    with app.app_context():
        _set_config('wstep_enabled', 'false')


def test_unrelated_field_change_does_not_restart(client, app, auth_client):
    with app.app_context():
        _set_config('wstep_enabled', 'false')
    _clear_restart_signal(app)

    r = auth_client.patch('/api/v2/windows-profiles/settings', json={'kerberos_spn': ''})
    assert r.status_code == 200
    assert 'restarting' not in r.get_json()['message'].lower()

    with app.app_context():
        assert not _restart_signal_path(app).exists()


def test_in_ha_the_switch_answers_a_rolling_listener_reload(app, auth_client, monkeypatch):
    """HA: the rolling restart is queued with the switch, and the answer says so as elsewhere."""
    from models import ClusterCommand
    from services.cluster_commands import RESTART
    from utils.listener_tls import ROLLING
    monkeypatch.setattr('utils.ha.ha_enabled', lambda: True)
    with app.app_context():
        _set_config('wstep_enabled', 'false')
        last = db.session.query(db.func.max(ClusterCommand.id)).scalar() or 0
    try:
        r = auth_client.patch('/api/v2/windows-profiles/settings', json={'wstep_enabled': True})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['data'] == {'listener_reload': ROLLING}
        with app.app_context():
            assert [c.kind for c in ClusterCommand.query.filter(ClusterCommand.id > last)] == [RESTART]
    finally:
        with app.app_context():
            ClusterCommand.query.filter(ClusterCommand.id > last).delete()
            db.session.commit()
            _set_config('wstep_enabled', 'false')
