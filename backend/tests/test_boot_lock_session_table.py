"""HA startup: Flask-Session creates its table while the node holds the boot lock,
so two nodes starting on an empty schema never race on CREATE TABLE."""
import contextlib

from services import scheduler_leader
from tests.fresh_app import fresh_app


def test_session_store_is_built_under_the_boot_lock(monkeypatch):
    import app as app_module

    held = []

    @contextlib.contextmanager
    def recording_lock(url, timeout=None, key=None):
        held.append(url)
        try:
            yield
        finally:
            held.pop()

    built_while_held = []
    real_session = app_module.Session

    def session_spy(application):
        built_while_held.append(bool(held))
        return real_session(application)

    monkeypatch.setattr(scheduler_leader, 'boot_lock', recording_lock)
    monkeypatch.setattr(app_module, 'Session', session_spy)
    with fresh_app():
        pass
    assert built_while_held == [True]
