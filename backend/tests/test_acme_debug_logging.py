"""Tests for ACME debug logging toggle."""
import pytest

from services.acme.acme_debug import CONFIG_KEY, acme_debug_logging_enabled, acme_log


@pytest.fixture(autouse=True)
def _clear_acme_debug_setting(app):
    with app.app_context():
        from models import SystemConfig, db
        cfg = SystemConfig.query.filter_by(key=CONFIG_KEY).first()
        if cfg:
            db.session.delete(cfg)
            db.session.commit()
    yield


def test_acme_debug_logging_disabled_by_default(app):
    with app.app_context():
        assert acme_debug_logging_enabled() is False


def test_acme_debug_logging_enabled(app, monkeypatch):
    from models import SystemConfig, db

    with app.app_context():
        db.session.add(SystemConfig(key=CONFIG_KEY, value='true', description='test'))
        db.session.commit()
        assert acme_debug_logging_enabled() is True


def test_acme_log_uses_info_when_debug_enabled(app, monkeypatch, caplog):
    import logging
    from models import SystemConfig, db

    caplog.set_level(logging.DEBUG)
    test_logger = logging.getLogger('test.acme_debug')

    with app.app_context():
        db.session.add(SystemConfig(key=CONFIG_KEY, value='true', description='test'))
        db.session.commit()
        acme_log(test_logger, 'visible diagnostic %s', 'ping')

    assert any('visible diagnostic ping' in r.message and r.levelname == 'INFO'
               for r in caplog.records)


def test_acme_log_uses_debug_when_disabled(app, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    test_logger = logging.getLogger('test.acme_debug')

    with app.app_context():
        acme_log(test_logger, 'hidden diagnostic %s', 'ping')

    assert any('hidden diagnostic ping' in r.message and r.levelname == 'DEBUG'
               for r in caplog.records)
