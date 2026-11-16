"""The leak guard of conftest counts the tables it names: a name the schema lacks is counted nowhere."""
import sys

from models import db


def test_every_table_the_leak_guard_watches_exists(app):
    conftest = sys.modules.get('tests.conftest') or sys.modules['conftest']
    with app.app_context():
        known = set(db.metadata.tables)
    watched = (*conftest._LEAK_TABLES, *conftest._LEAK_CONTENT)
    assert [name for name in watched if name not in known] == []
