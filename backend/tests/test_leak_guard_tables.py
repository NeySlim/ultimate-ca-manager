"""The leak guard of conftest counts the tables it names: a name the schema lacks is counted nowhere."""
import sys

import pytest

from models import db


def test_every_table_the_leak_guard_watches_exists(app):
    conftest = sys.modules.get('tests.conftest') or sys.modules['conftest']
    with app.app_context():
        known = set(db.metadata.tables)
    watched = (*conftest._LEAK_TABLES, *conftest._LEAK_CONTENT)
    assert [name for name in watched if name not in known] == []


@pytest.mark.sqlite_only('PostgreSQL refuses a row naming a missing account')
def test_the_leak_guard_counts_acme_rows_whose_account_is_gone(app):
    conftest = sys.modules.get('tests.conftest') or sys.modules['conftest']
    from models.acme_models import AcmeAuthorization, AcmeOrder
    before = conftest._leak_counts()
    with app.app_context():
        db.session.add(AcmeOrder(account_id='flk7-account-gone', identifiers='[]'))
        db.session.add(AcmeAuthorization(account_id='flk7-account-gone', identifier='{}'))
        db.session.commit()
    try:
        after = conftest._leak_counts()
        for label in conftest._ORPHAN_ACME:
            assert after[label] == before[label] + 1, label
    finally:
        with app.app_context():
            AcmeAuthorization.query.filter_by(account_id='flk7-account-gone').delete()
            AcmeOrder.query.filter_by(account_id='flk7-account-gone').delete()
            db.session.commit()
