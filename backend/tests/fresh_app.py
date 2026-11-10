"""An app on an empty database of its own, for the files whose cost grows with the session one.

A backup serialises the whole database: on the session app, after hundreds of
files have filled it, each archive took tens of seconds. A file opts in with

    app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

at module level, or inside a class with ``fresh_app_fixtures('class')``.
"""
import contextlib
import shutil
import tempfile
from pathlib import Path

import pytest

from tests.conftest import (
    admin_client, ca_factory, cert_factory, clear_admin_password_flag,
    configure_test_app, sandbox_paths, user_factory,
)

_UNSET = object()


@contextlib.contextmanager
def fresh_app():
    """create_app('testing') on its own database; paths, session store and scheduler put back on exit."""
    from app import create_app
    from config.settings import Config, config
    from models import db
    from services import scheduler_service

    # create_app replaces the process-wide scheduler with one bound to the new app.
    scheduler = scheduler_service._scheduler
    # A store of its own, bound when create_app builds the session interface:
    # a restore empties the store, which signed the session app's clients out.
    sessions = Path(tempfile.mkdtemp(prefix='ucm-test-sessions-'))
    # TestingConfig may define its own SESSION_FILE_DIR (database session type), which shadows Config's.
    holders = (Config, config['testing'])
    shared_sessions = [holder.__dict__.get('SESSION_FILE_DIR', _UNSET) for holder in holders]
    for holder in holders:
        holder.SESSION_FILE_DIR = sessions
    application = sandbox = None
    replaced = {}
    try:
        try:
            application = create_app('testing')
        finally:
            for holder, previous in zip(holders, shared_sessions):
                if previous is _UNSET:
                    del holder.SESSION_FILE_DIR
                else:
                    holder.SESSION_FILE_DIR = previous
        sandbox, _ = sandbox_paths(application, replaced)
        configure_test_app(application)
        clear_admin_password_flag(application)
        yield application
    finally:
        # Also after a failed build: the next files inherit whatever is left here.
        if application is not None:
            with application.app_context():
                db.session.remove()
                db.engine.dispose()
        for name, value in replaced.items():
            setattr(Config, name, value)
        scheduler_service._scheduler = scheduler
        if sandbox is not None:
            shutil.rmtree(sandbox, ignore_errors=True)
        shutil.rmtree(sessions, ignore_errors=True)

def fresh_app_fixtures(scope='module'):
    """The fixtures `app`, `auth_client`, `create_ca`, `create_cert`, `create_user` on a fresh app.

    `*_bound` takes the instance when they are class attributes; the fixtures they
    depend on are keyword-only, which pytest resolves by name either way.
    """

    @pytest.fixture(scope=scope)
    def app(*_bound):
        with fresh_app() as application:
            yield application

    @pytest.fixture(scope=scope)
    def auth_client(*_bound, app):
        return admin_client(app)

    @pytest.fixture(scope=scope)
    def create_ca(*_bound, auth_client):
        return ca_factory(auth_client)

    @pytest.fixture(scope=scope)
    def create_cert(*_bound, auth_client, create_ca):
        return cert_factory(auth_client, create_ca)

    @pytest.fixture(scope=scope)
    def create_user(*_bound, auth_client):
        return user_factory(auth_client)

    return app, auth_client, create_ca, create_cert, create_user
