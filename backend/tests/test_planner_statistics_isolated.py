"""ANALYZE leaves sqlite_stat1 in the database every later file shares; the suite drops it after each file."""
import pytest
from sqlalchemy import text

from models import db
from tests import conftest


def _has_statistics():
    return db.session.execute(text("SELECT 1 FROM sqlite_master WHERE name = 'sqlite_stat1'")).first() is not None


def test_the_statistics_an_analyze_left_are_dropped(app):
    with app.app_context():
        if db.engine.dialect.name != 'sqlite':
            pytest.skip('SQLite planner statistics')
        db.session.execute(text('ANALYZE'))
        db.session.commit()
        db.session.remove()
    conftest._drop_planner_statistics()
    with app.app_context():
        assert not _has_statistics()
