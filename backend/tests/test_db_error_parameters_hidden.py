"""A database error's text never quotes the row: private keys pass through these engines."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config.settings import Config
from models import db
from services.database_admin import copy as copy_module
from services.database_admin import migration


class _Stop(Exception):
    pass


def _recording(built):
    def create_engine(*_args, **kwargs):
        built.append(kwargs)
        raise _Stop
    return create_engine


def test_the_application_engine_hides_them(app):
    assert Config.SQLALCHEMY_ENGINE_OPTIONS['hide_parameters'] is True
    with app.app_context(), db.engine.connect() as conn, pytest.raises(SQLAlchemyError) as caught:
        conn.execute(text('INSERT INTO no_such_table VALUES (:secret)'), {'secret': 'PRIVATE-KEY-MATERIAL'})
    assert 'PRIVATE-KEY-MATERIAL' not in str(caught.value)


@pytest.mark.parametrize('copy_rows', [migration.bootstrap_auth_to_target, migration.migrate_data])
def test_a_migration_target_hides_them(app, copy_rows):
    built = []
    with app.app_context(), patch.object(migration, 'create_engine', _recording(built)), \
            patch.object(migration, 'test_connection', return_value=(True, 'ok')):
        try:
            copy_rows('sqlite:////nonexistent/target.db')
        except _Stop:
            pass
    assert built and all(kwargs.get('hide_parameters') is True for kwargs in built)


def test_a_snapshot_source_hides_them():
    built = []
    with patch.object(copy_module, 'create_engine', _recording(built)), pytest.raises(_Stop):
        with copy_module.consistent_source(SimpleNamespace(backend='sqlite', path='/nonexistent/snap.db')):
            pass
    assert built[0].get('hide_parameters') is True
