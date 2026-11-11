"""After a restore, every authority that publishes a CRL and can sign gets a fresh one at once,
and one that cannot sign is reported, never a failed restore."""
import pytest

from models import CA, db
from models.crl import CRLMetadata
from services.backup.restore.invalidate import invalidate_after_restore
from services.backup.restore_report import with_restore_warnings


@pytest.fixture(autouse=True)
def session_store(app, tmp_path, monkeypatch):
    store = tmp_path / 'sessions'
    store.mkdir()
    monkeypatch.setitem(app.config, 'SESSION_FILE_DIR', str(store))


def _publishing(app, create_ca, cn, **columns):
    ca = create_ca(cn=cn)
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        row.cdp_enabled = True
        for name, value in columns.items():
            setattr(row, name, value)
        db.session.commit()
        return row.id, row.descr


def _latest(ca_id, delta=False):
    row = CRLMetadata.query.filter_by(ca_id=ca_id, is_delta=delta) \
        .order_by(CRLMetadata.crl_number.desc()).first()
    return row.crl_number if row else None


def test_a_publishing_authority_gets_a_new_crl_and_its_delta(app, create_ca, monkeypatch):
    ca_id, name = _publishing(app, create_ca, 'Restore CRL CA', delta_crl_enabled=True)
    events = []
    from services.events import event_bus
    real_emit = event_bus.emit
    monkeypatch.setattr(event_bus, 'emit', lambda kind, payload, **kw: (
        events.append((kind, payload)), real_emit(kind, payload, **kw)))
    with app.app_context():
        before, before_delta = _latest(ca_id), _latest(ca_id, delta=True)
        result = invalidate_after_restore()
        assert name in result['crls_regenerated'], result
        assert name not in result['crls_failed']
        assert _latest(ca_id) is not None and _latest(ca_id) != before
        assert _latest(ca_id, delta=True) is not None and _latest(ca_id, delta=True) != before_delta
    assert any(kind == 'crl.updated' and payload['crl']['ca_id'] == ca_id
               for kind, payload in events), events


def test_an_authority_that_cannot_sign_is_reported_and_the_others_still_get_theirs(
        app, create_ca, monkeypatch):
    good_id, good = _publishing(app, create_ca, 'Restore CRL Good')
    bad_id, bad = _publishing(app, create_ca, 'Restore CRL No HSM')
    from services.hsm import ca_key_loader
    real = ca_key_loader.get_ca_signing_key

    def signing_key(ca, **kw):
        if ca.id == bad_id:
            raise RuntimeError('HSM token not present')
        return real(ca, **kw)
    monkeypatch.setattr(ca_key_loader, 'get_ca_signing_key', signing_key)
    with app.app_context():
        result = invalidate_after_restore()
        assert bad in result['crls_failed'] and bad not in result['crls_regenerated']
        assert good in result['crls_regenerated']
        assert _latest(good_id) is not None


def test_an_authority_without_a_distribution_point_is_left_alone(app, create_ca):
    ca = create_ca(cn='Restore CRL No CDP')
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        row.cdp_enabled = False
        db.session.commit()
        before = _latest(row.id)
        result = invalidate_after_restore()
        assert row.descr not in result['crls_regenerated']
        assert _latest(row.id) == before


def test_the_restore_message_names_the_authorities_left_without_a_crl():
    message = with_restore_warnings('Backup restored successfully.',
                                    {'invalidated': {'crls_failed': ['Issuing HSM CA']}})
    assert 'Issuing HSM CA' in message and 'CRL' in message


@pytest.mark.parametrize('route', ('/api/v2/system/restore', '/api/v2/settings/backup/restore'))
def test_both_restore_routes_name_an_authority_left_without_a_crl(app, auth_client, monkeypatch,
                                                                    route):
    import importlib
    from tests.test_restore_facade_parity import _upload
    for module in ('api.v2.system.backup', 'api.v2.settings.backup'):
        loaded = importlib.import_module(module)
        if hasattr(loaded, 'BackupService'):
            monkeypatch.setattr(loaded.BackupService, 'restore_backup',
                                lambda self, *a, **k: {'sections_carried': ['certificate_authorities']},
                                raising=False)
    import services.backup.restore.invalidate as invalidate
    monkeypatch.setattr(invalidate, 'invalidate_after_restore',
                        lambda *a, **k: {'crls_regenerated': [], 'crls_failed': ['Unsigned HSM CA']})
    monkeypatch.setattr('utils.service_manager.restart_service', lambda *a, **k: (False, 'no'))
    response = _upload(auth_client, route)
    assert response.status_code == 200, response.get_json()
    assert 'Unsigned HSM CA' in response.get_json()['message']
