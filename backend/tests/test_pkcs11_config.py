"""Tests for PKCS#11 config key normalization (PR #194)."""

import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.hsm import HsmProvider
from utils.pkcs11_config import (
    normalize_pkcs11_config,
    pkcs11_config_needs_normalization,
)

try:
    import pkcs11 as _pkcs11  # noqa: F401
    _PKCS11_AVAILABLE = True
except ImportError:
    _PKCS11_AVAILABLE = False


class TestNormalizePkcs11Config:
    def test_maps_legacy_keys(self):
        cfg = {
            'library_path': '/usr/lib/softhsm/libsofthsm2.so',
            'pin': '1234',
            'token_label': 'UCM-Default',
        }
        out = normalize_pkcs11_config(cfg)
        assert out['module_path'] == '/usr/lib/softhsm/libsofthsm2.so'
        assert out['user_pin'] == '1234'
        assert out['token_label'] == 'UCM-Default'
        assert 'library_path' not in out
        assert 'pin' not in out

    def test_canonical_keys_unchanged(self):
        cfg = {
            'module_path': '/lib.so',
            'user_pin': 'secret',
            'token_label': 'tok',
        }
        assert normalize_pkcs11_config(cfg) == cfg

    def test_needs_normalization_detects_legacy(self):
        assert pkcs11_config_needs_normalization({'library_path': '/x.so', 'pin': '1'})
        assert not pkcs11_config_needs_normalization(
            {'module_path': '/x.so', 'user_pin': '1'}
        )


class TestPkcs11ProviderLegacyConfig:
    pytestmark = pytest.mark.skipif(
        not _PKCS11_AVAILABLE,
        reason="python-pkcs11 not installed in this environment",
    )

    def test_accepts_library_path_and_pin(self, tmp_path):
        lib = tmp_path / 'fake.so'
        lib.write_bytes(b'\x00')

        from services.hsm.pkcs11_provider import Pkcs11Provider

        with patch.object(Pkcs11Provider, 'connect', return_value=True):
            provider = Pkcs11Provider({
                'library_path': str(lib),
                'pin': '1234',
                'token_label': 'test',
            })
        assert provider.module_path == str(lib)
        assert provider.user_pin == '1234'


class TestAutoRegisterSofthsm:
    def test_registers_with_canonical_keys(self, app):
        with app.app_context():
            HsmProvider.query.filter_by(name='SoftHSM-Default').delete()
            from models import db
            db.session.commit()

            fake_lib = '/tmp/libsofthsm-test.so'
            with patch.dict(os.environ, {'HSM_DEFAULT_PIN': '87654321'}), \
                 patch('utils.hsm_check._find_softhsm', return_value=fake_lib):
                from services.hsm.hsm_service import HsmService
                HsmService.auto_register_softhsm()

            row = HsmProvider.query.filter_by(name='SoftHSM-Default').first()
            assert row is not None
            cfg = row.get_config()
            assert cfg['module_path'] == fake_lib
            assert cfg['user_pin'] == '87654321'
            assert 'library_path' not in cfg
            assert 'pin' not in cfg

    def test_repairs_existing_legacy_row(self, app):
        with app.app_context():
            from models import db
            from services.hsm.hsm_service import HsmService

            HsmProvider.query.filter_by(name='SoftHSM-Default').delete()
            db.session.commit()

            legacy = HsmProvider(
                name='SoftHSM-Default',
                type='pkcs11',
                config='{}',
                status='unknown',
            )
            legacy.set_config({
                'library_path': '/usr/lib/legacy.so',
                'pin': 'legacy-pin',
                'token_label': 'UCM-Default',
            })
            db.session.add(legacy)
            db.session.commit()

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop('HSM_DEFAULT_PIN', None)
                HsmService.auto_register_softhsm()

            cfg = legacy.get_config()
            assert cfg['module_path'] == '/usr/lib/legacy.so'
            assert cfg['user_pin'] == 'legacy-pin'
            assert 'library_path' not in cfg
            assert 'pin' not in cfg


    @staticmethod
    def _seed_row(config, status='connected', error_message=None):
        from models import db

        HsmProvider.query.filter_by(name='SoftHSM-Default').delete()
        db.session.commit()
        row = HsmProvider(name='SoftHSM-Default', type='pkcs11', config='{}', status=status,
                          error_message=error_message)
        row.set_config({'module_path': '/usr/lib/softhsm/libsofthsm2.so', **config})
        db.session.add(row)
        db.session.commit()
        return row

    @staticmethod
    def _run(env):
        from services.hsm.hsm_service import HsmService

        with patch.dict(os.environ, env):
            for name in ('HSM_DEFAULT_PIN', 'HSM_TOKEN_CREATED', 'HSM_TOKENS_MOVED'):
                if name not in env:
                    os.environ.pop(name, None)
            HsmService.auto_register_softhsm()

    @pytest.mark.parametrize('label', [{'token_label': 'UCM-Default'}, {}], ids=['label-set', 'label-absent'])
    def test_a_new_token_takes_over_the_existing_row(self, app, caplog, label):
        """The entrypoint only creates UCM-Default when it is missing: the stored PIN opened a token that is gone."""
        with app.app_context():
            from models import db

            row = self._seed_row({**label, 'user_pin': 'stale-pin'}, status='error',
                                 error_message='PKCS#11 connection failed')
            self._run({'HSM_DEFAULT_PIN': 'fresh-pin', 'HSM_TOKEN_CREATED': '1'})

            db.session.refresh(row)
            cfg = row.get_config()
            assert cfg['user_pin'] == 'fresh-pin'
            assert cfg['previous_user_pin'] == 'stale-pin'
            assert cfg['token_label'] == 'UCM-Default'
            assert cfg['module_path'] == '/usr/lib/softhsm/libsofthsm2.so'
            assert HsmProvider.query.filter_by(name='SoftHSM-Default').count() == 1
            assert row.status == 'unknown'
            assert row.error_message is None
            assert 'created anew' in caplog.text
            assert 'Repaired PKCS#11 config keys' not in caplog.text
            assert 'stale-pin' not in row.config
            assert row.to_dict(include_config=True)['config']['previous_user_pin'] == '********'

    def test_a_second_takeover_keeps_the_oldest_pin(self, app):
        """The token a moved volume brings back is the first one, not the one created in between."""
        with app.app_context():
            from models import db

            row = self._seed_row({'token_label': 'UCM-Default', 'user_pin': 'second-pin',
                                  'previous_user_pin': 'first-pin'})
            self._run({'HSM_DEFAULT_PIN': 'third-pin', 'HSM_TOKEN_CREATED': '1'})

            db.session.refresh(row)
            assert row.get_config()['user_pin'] == 'third-pin'
            assert row.get_config()['previous_user_pin'] == 'first-pin'

    def test_editing_the_provider_keeps_the_previous_pin(self, app):
        """The form sends only its own fields; the kept PIN is not one of them."""
        with app.app_context():
            from services.hsm.hsm_service import HsmService

            row = self._seed_row({'token_label': 'UCM-Default', 'user_pin': 'fresh-pin',
                                  'previous_user_pin': 'stale-pin'})
            HsmService.update_provider(row.id, config={
                'module_path': '/usr/lib/softhsm/libsofthsm2.so', 'token_label': 'UCM-Default', 'user_pin': '***'})

            row = HsmProvider.query.filter_by(name='SoftHSM-Default').one()
            assert row.get_config()['user_pin'] == 'fresh-pin'
            assert row.get_config()['previous_user_pin'] == 'stale-pin'

    def test_tokens_carried_over_get_their_old_pin_back(self, app, caplog):
        """Started once without the old volume, then with it: the old token is back, so is its PIN."""
        with app.app_context():
            from models import db

            row = self._seed_row({'token_label': 'UCM-Default', 'user_pin': 'fresh-pin',
                                  'previous_user_pin': 'stale-pin'})
            self._run({'HSM_TOKENS_MOVED': '1'})

            db.session.refresh(row)
            cfg = row.get_config()
            assert cfg['user_pin'] == 'stale-pin'
            assert 'previous_user_pin' not in cfg
            assert row.status == 'unknown'
            assert 'carried over' in caplog.text

    @pytest.mark.parametrize('env, config', [
        ({'HSM_DEFAULT_PIN': 'env-pin'}, {'token_label': 'UCM-Default'}),
        ({'HSM_DEFAULT_PIN': 'env-pin', 'HSM_TOKEN_CREATED': '1'}, {'token_label': 'MyToken'}),
        ({'HSM_TOKENS_MOVED': '1'}, {'token_label': 'UCM-Default'}),
        ({'HSM_TOKENS_MOVED': '1'}, {'token_label': 'MyToken', 'previous_user_pin': 'other-pin'}),
    ], ids=['pin-kept-in-ucm-env', 'row-aimed-at-another-token', 'moved-without-previous-pin',
            'moved-row-aimed-at-another-token'])
    def test_an_existing_row_is_left_alone(self, app, caplog, env, config):
        """A native install keeps HSM_DEFAULT_PIN in ucm.env for good, and an admin may aim the row elsewhere."""
        with app.app_context():
            from models import db

            row = self._seed_row({**config, 'user_pin': 'admin-pin'})
            self._run(env)

            db.session.refresh(row)
            assert row.get_config()['user_pin'] == 'admin-pin'
            assert row.get_config()['token_label'] == config['token_label']
            assert row.status == 'connected'
            assert 'created anew' not in caplog.text
            assert 'carried over' not in caplog.text


class TestMigration057:
    def test_sqlite_rewrites_legacy_config(self, tmp_path):
        import importlib.util
        import sqlite3
        from pathlib import Path

        mig_path = (
            Path(__file__).resolve().parents[1]
            / 'migrations'
            / '057_pkcs11_config_keys.py'
        )
        spec = importlib.util.spec_from_file_location('migration_057', mig_path)
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)

        db_path = tmp_path / 'hsm.db'
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE hsm_providers (id INTEGER PRIMARY KEY, type TEXT, config TEXT)"
        )
        legacy = json.dumps({
            'library_path': '/old.so',
            'pin': 'abcd',
            'token_label': 'tok',
        })
        conn.execute(
            "INSERT INTO hsm_providers (id, type, config) VALUES (1, 'pkcs11', ?)",
            (legacy,),
        )
        conn.commit()

        mig.upgrade(conn)

        row = conn.execute(
            "SELECT config FROM hsm_providers WHERE id = 1"
        ).fetchone()
        cfg = json.loads(row[0])
        assert cfg['module_path'] == '/old.so'
        assert cfg['user_pin'] == 'abcd'
        assert 'library_path' not in cfg
        assert 'pin' not in cfg
        conn.close()
