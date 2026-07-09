"""Tests for ACME debug logging toggle."""
import logging
from unittest.mock import MagicMock

import pytest

from utils.acme_debug import (
    CONFIG_KEY,
    acme_debug_logging_enabled,
    acme_log,
    clear_acme_debug_cache,
)


@pytest.fixture(autouse=True)
def _clear_acme_debug_setting(app):
    with app.app_context():
        from models import SystemConfig, db
        cfg = SystemConfig.query.filter_by(key=CONFIG_KEY).first()
        if cfg:
            db.session.delete(cfg)
            db.session.commit()
        clear_acme_debug_cache()
    yield


def test_acme_debug_logging_disabled_by_default(app):
    with app.app_context():
        assert acme_debug_logging_enabled() is False


def test_acme_debug_logging_enabled(app):
    from models import SystemConfig, db

    with app.app_context():
        db.session.add(SystemConfig(key=CONFIG_KEY, value='true', description='test'))
        db.session.commit()
        clear_acme_debug_cache()
        assert acme_debug_logging_enabled() is True


def test_acme_debug_logging_memoized_per_app_context(app, monkeypatch):
    import utils.acme_debug as debug_mod

    query_mock = MagicMock()
    cfg = MagicMock()
    cfg.value = 'true'
    query_mock.filter_by.return_value.first.return_value = cfg
    sc_mock = MagicMock()
    sc_mock.query = query_mock

    with app.app_context():
        clear_acme_debug_cache()
        monkeypatch.setattr(debug_mod, 'SystemConfig', sc_mock)
        assert acme_debug_logging_enabled() is True
        assert acme_debug_logging_enabled() is True
        assert query_mock.filter_by.call_count == 1


def test_acme_log_uses_info_when_debug_enabled(app, caplog):
    from models import SystemConfig, db

    caplog.set_level(logging.DEBUG)
    test_logger = logging.getLogger('test.acme_debug')

    with app.app_context():
        db.session.add(SystemConfig(key=CONFIG_KEY, value='true', description='test'))
        db.session.commit()
        clear_acme_debug_cache()
        acme_log(test_logger, 'visible diagnostic %s', 'ping')

    assert any(
        'visible diagnostic ping' in r.message and r.levelname == 'INFO'
        for r in caplog.records
    )


def test_acme_log_uses_debug_when_disabled(app, caplog):
    caplog.set_level(logging.DEBUG)
    test_logger = logging.getLogger('test.acme_debug')

    with app.app_context():
        acme_log(test_logger, 'hidden diagnostic %s', 'ping')

    assert any(
        'hidden diagnostic ping' in r.message and r.levelname == 'DEBUG'
        for r in caplog.records
    )
