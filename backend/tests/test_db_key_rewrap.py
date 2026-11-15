"""Re-encryption of the integration secrets from the machine-derived key to UCM_DB_ENCRYPTION_KEY.

Runs on SQLite and, through scripts/ci/pg-app-tests.txt, on PostgreSQL. Its rows are
created here, found by id and deleted; the scan is narrowed to them so that another
file's rows never decide the outcome.
"""
import json
import logging
import uuid

import pytest
from cryptography.fernet import Fernet

import services.db_key_rewrap as rewrap_mod
import utils.encryption as enc
from models import db

PLAIN = {'webhook': 'webhook-signing-secret-0123456789',
         'token': 'bearer-token-abcdef',
         'dns': json.dumps({'api_token': 'dns-api-token-xyz'}),
         'pin': 'hsm-user-pin-4242',
         'backup': 'Backup-Password-123!'}


@pytest.fixture
def old_key():
    return Fernet.generate_key()


@pytest.fixture
def rows(app, old_key, monkeypatch):
    """One secret of each kind, under the old (machine-derived) key."""
    from models import SystemConfig
    from models.acme_models import DnsProvider
    from models.hsm import HsmProvider
    from services.webhook_service import WebhookEndpoint
    old = Fernet(old_key)
    tag = uuid.uuid4().hex[:8]

    def seal(text):
        return old.encrypt(text.encode()).decode()

    with app.app_context():
        wh = WebhookEndpoint(name=f'rewrap-{tag}', url='https://hooks.example/r', auth_type='bearer',
                             secret=seal(PLAIN['webhook']))
        wh._auth_token = seal(PLAIN['token'])
        dns = DnsProvider(name=f'rewrap-{tag}', provider_type='cloudflare')
        dns._credentials = seal(PLAIN['dns'])
        hsm = HsmProvider(name=f'rewrap-{tag}', type='pkcs11',
                          config=json.dumps({'library_path': '/lib/x.so', 'user_pin': seal(PLAIN['pin'])}))
        setting = SystemConfig(key=f'rewrap.{tag}.backup_password', value=seal(PLAIN['backup']), encrypted=True)
        db.session.add_all([wh, dns, hsm, setting])
        db.session.commit()
        ids = {'wh': wh.id, 'dns': dns.id, 'hsm': hsm.id, 'setting': setting.key}

    real = rewrap_mod.secret_values
    mine = {f'webhook_endpoints {ids["wh"]} secret', f'webhook_endpoints {ids["wh"]} _auth_token',
            f'dns_providers {ids["dns"]} credentials', f'hsm_providers {ids["hsm"]} config',
            f'system_config {ids["setting"]} value'}
    monkeypatch.setattr(rewrap_mod, 'secret_values', lambda: [s for s in real() if s.label in mine])
    ids['labels'] = mine
    yield ids
    with app.app_context():
        db.session.rollback()
        db.session.delete(db.session.get(WebhookEndpoint, ids['wh']))
        db.session.delete(db.session.get(DnsProvider, ids['dns']))
        db.session.delete(db.session.get(HsmProvider, ids['hsm']))
        SystemConfig.query.filter_by(key=ids['setting']).delete()
        db.session.commit()


def _read_back(ids):
    """Every secret read the way its integration reads it, under the current key."""
    from models import SystemConfig
    from models.acme_models import DnsProvider
    from models.hsm import HsmProvider
    from services.webhook_service import WebhookEndpoint
    db.session.expire_all()
    wh = db.session.get(WebhookEndpoint, ids['wh'])
    return {'webhook': enc.decrypt_required(wh.secret, 'w'),
            'token': enc.decrypt_required(wh._auth_token, 't'),
            'dns': enc.decrypt_required(db.session.get(DnsProvider, ids['dns'])._credentials, 'd'),
            'pin': db.session.get(HsmProvider, ids['hsm']).get_config()['user_pin'],
            'backup': enc.decrypt_required(SystemConfig.query.filter_by(key=ids['setting']).one().value, 'b')}


def _current_key():
    import os
    return os.environ['UCM_DB_ENCRYPTION_KEY'].encode()


def test_unreadable_secrets_names_what_the_current_key_does_not_open(app, rows):
    with app.app_context():
        assert sorted(rewrap_mod.unreadable_secrets()) == sorted(rows['labels'])


def test_rewrap_moves_every_kind_of_secret_under_the_new_key(app, rows, old_key):
    with app.app_context():
        result = rewrap_mod.rewrap([old_key], _current_key())
        assert result['rewritten'] == 5
        assert _read_back(rows) == PLAIN
        assert rewrap_mod.unreadable_secrets() == []


def test_rewrap_is_idempotent(app, rows, old_key):
    with app.app_context():
        rewrap_mod.rewrap([old_key], _current_key())
        again = rewrap_mod.rewrap([old_key], _current_key())
        assert again == {'rewritten': 0, 'to_rewrite': 0, 'already': 5}
        assert _read_back(rows) == PLAIN


def test_dry_run_writes_nothing(app, rows, old_key):
    with app.app_context():
        result = rewrap_mod.rewrap([old_key], _current_key(), dry_run=True)
        assert result['to_rewrite'] == 5
        assert sorted(rewrap_mod.unreadable_secrets()) == sorted(rows['labels'])


def test_a_secret_no_key_opens_stops_the_run_before_any_write(app, rows, old_key):
    from services.webhook_service import WebhookEndpoint
    with app.app_context():
        wh = db.session.get(WebhookEndpoint, rows['wh'])
        wh._auth_token = Fernet(Fernet.generate_key()).encrypt(b'lost').decode()
        db.session.commit()
        with pytest.raises(rewrap_mod.RewrapRefused) as err:
            rewrap_mod.rewrap([old_key], _current_key())
        assert err.value.labels == [f'webhook_endpoints {rows["wh"]} _auth_token']
        # Nothing moved: the other secrets are still under the old key only
        assert len(rewrap_mod.unreadable_secrets()) == 5


def test_the_command_never_prints_or_logs_a_secret(app, rows, old_key, monkeypatch, capsys, caplog):
    from scripts import rewrap_db_key
    monkeypatch.setattr(rewrap_db_key, '_app', lambda: app)
    monkeypatch.setattr(enc, 'machine_derived_key', lambda create=True: old_key)
    with caplog.at_level(logging.DEBUG):
        assert rewrap_db_key.main([]) == 0
        assert rewrap_db_key.main([]) == 0
    out = capsys.readouterr()
    assert '5 secret(s) re-encrypted' in out.out and '0 secret(s) re-encrypted, 5 already' in out.out
    text = out.out + out.err + caplog.text
    for value in PLAIN.values():
        assert value not in text
    with app.app_context():
        assert _read_back(rows) == PLAIN


def test_the_command_names_what_it_refuses(app, rows, monkeypatch, capsys):
    from scripts import rewrap_db_key
    monkeypatch.setattr(rewrap_db_key, '_app', lambda: app)
    monkeypatch.setattr(enc, 'machine_derived_key', lambda create=True: Fernet.generate_key())
    assert rewrap_db_key.main([]) == 1
    err = capsys.readouterr().err
    assert f'webhook_endpoints {rows["wh"]} secret' in err and 'nothing was written' in err


def test_the_command_reads_a_previous_explicit_key(app, rows, old_key, monkeypatch):
    from scripts import rewrap_db_key
    monkeypatch.setattr(rewrap_db_key, '_app', lambda: app)
    monkeypatch.setenv('OLD_DB_KEY', old_key.decode())
    assert rewrap_db_key.main(['--from-env', 'OLD_DB_KEY']) == 0
    with app.app_context():
        assert _read_back(rows) == PLAIN


def test_the_command_needs_the_new_key(monkeypatch):
    from scripts import rewrap_db_key
    monkeypatch.setenv('UCM_DB_ENCRYPTION_KEY', 'not-a-key')
    assert rewrap_db_key.main([]) == 2


def test_ha_start_reports_the_secrets_it_cannot_open(app, rows, caplog):
    with app.app_context(), caplog.at_level(logging.ERROR):
        labels = rewrap_mod.report_unreadable_at_start()
    assert sorted(labels) == sorted(rows['labels'])
    assert 'scripts.rewrap_db_key' in caplog.text
    for value in PLAIN.values():
        assert value not in caplog.text


def test_a_value_changed_during_the_run_is_not_overwritten(app, rows, old_key, monkeypatch):
    from services.webhook_service import WebhookEndpoint
    with app.app_context():
        stale = rewrap_mod.secret_values()
        newer = Fernet(old_key).encrypt(b'entered-meanwhile').decode()
        db.session.get(WebhookEndpoint, rows['wh']).secret = newer
        db.session.commit()
        monkeypatch.setattr(rewrap_mod, 'secret_values', lambda: stale)
        with pytest.raises(RuntimeError, match='changed during the run'):
            rewrap_mod.rewrap([old_key], _current_key())
        db.session.expire_all()
        assert db.session.get(WebhookEndpoint, rows['wh']).secret == newer
