"""An HSM provider's PIN survives a restore under another database key: the archive holds it in clear."""
import json

import pytest
from cryptography.fernet import Fernet

from models import db
from models.hsm import HsmProvider
from services.backup.key_material import decrypt_stored_fields
from services.backup.manifest import SECTIONS
from services.backup.restore.apply import _secret_as_stored
from utils import encryption


@pytest.fixture
def under_key(monkeypatch):
    def use(key):
        monkeypatch.setattr(encryption, 'get_cipher', lambda: Fernet(key))
    return use


def _stored_config(values):
    provider = HsmProvider(name='hsm-pin', type='pkcs11')
    provider.set_config(values)
    return provider.config


def _restored(archived):
    provider = HsmProvider(name='hsm-pin', type='pkcs11')
    provider.config = _secret_as_stored(SECTIONS['hsm_providers'], 'config', archived)
    return provider


def test_the_pin_reads_back_under_another_key_and_stays_encrypted(app, under_key):
    values = {'module': '/usr/lib/softhsm.so', 'pin': '1234', 'slot': 3}
    under_key(Fernet.generate_key())
    stored = _stored_config(values)
    assert json.loads(stored)['pin'] != '1234'

    archived = decrypt_stored_fields(stored, label='hsm')
    assert json.loads(archived) == values

    under_key(Fernet.generate_key())
    restored = _restored(archived)
    assert restored.get_config() == values
    assert json.loads(restored.config)['pin'].startswith('gAAAA')


def test_a_field_it_cannot_open_does_not_stop_the_backup(app, under_key, caplog):
    under_key(Fernet.generate_key())
    stored = _stored_config({'pin': '1234', 'slot': 3})
    under_key(Fernet.generate_key())
    assert json.loads(decrypt_stored_fields(stored, label='hsm')) == json.loads(stored)
    assert 'field pin is encrypted under another key' in caplog.text


def test_only_a_sensitive_field_is_a_secret(app, under_key, caplog):
    # A label may look like a token: get_config would never decrypt it
    lookalike = 'gAAAAA' + 'x' * 60
    under_key(Fernet.generate_key())
    assert json.loads(decrypt_stored_fields(json.dumps({'token_label': lookalike}), label='hsm')) == \
        {'token_label': lookalike}
    assert 'another key' not in caplog.text
    restored = _secret_as_stored(SECTIONS['hsm_providers'], 'config', json.dumps({'token_label': lookalike}))
    assert json.loads(restored) == {'token_label': lookalike}


def test_an_older_archive_restores_on_its_own_key_and_warns_on_another(app, under_key, caplog):
    source = Fernet.generate_key()
    under_key(source)
    archived = _stored_config({'pin': '1234'})  # what the export used to write

    assert _restored(archived).get_config() == {'pin': '1234'}
    assert 'another' not in caplog.text

    under_key(Fernet.generate_key())
    assert _restored(archived).get_config() == {}
    assert "lost field pin" in caplog.text


@pytest.mark.parametrize('value', ['not json', '["a"]'])
def test_a_config_that_is_no_object_is_left_as_it_is(app, value):
    assert decrypt_stored_fields(value, label='hsm') == value
    assert _secret_as_stored(SECTIONS['hsm_providers'], 'config', value) == value
