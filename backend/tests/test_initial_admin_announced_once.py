"""Where the generated password is: said by the web process, not again by the scheduler process."""
from tests.fresh_app import fresh_app


def _announces(monkeypatch, scheduler):
    from app import init_database
    from auth import initial_admin
    seen = []
    monkeypatch.setattr(initial_admin, 'announce', lambda config: seen.append(1))
    if scheduler:
        monkeypatch.setenv('UCM_SCHEDULER_PROCESS', '1')
    else:
        monkeypatch.delenv('UCM_SCHEDULER_PROCESS', raising=False)
    with fresh_app() as application, application.app_context():
        init_database(application)
    return len(seen)


def test_the_web_process_announces_the_password_file(monkeypatch):
    assert _announces(monkeypatch, scheduler=False) > 0


def test_the_scheduler_process_does_not_repeat_it(monkeypatch):
    assert _announces(monkeypatch, scheduler=True) == 0
