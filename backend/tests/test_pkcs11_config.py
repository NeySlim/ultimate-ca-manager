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
