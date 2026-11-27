"""count_master_key_values counts in SQL: same answer as walking every row, a handful of queries."""
import base64

import pytest
from sqlalchemy import event

from models import SystemConfig, db
from security import encryption as enc

ENCRYPTED = base64.b64encode(enc.ENCRYPTED_MARKER + b'x' * 40).decode()
KEYS = {
    'acme.client.eab_hmac_key': ENCRYPTED,
    'acme.proxy.eab_hmac_key': 'plain-secret',
    'acme.account.7.private_key': 'plain-too',
    'acme.account.8.private_key': ENCRYPTED,
    'acme.unrelated': 'plain-not-a-secret',
}


def _walk():
    encrypted = unencrypted = 0
    for _, row, attribute, _fmt in enc.master_key_values():
        if enc.key_encryption.is_encrypted(getattr(row, attribute)):
            encrypted += 1
        else:
            unencrypted += 1
    return encrypted, unencrypted


@pytest.fixture
def seeded(app):
    with app.app_context():
        for k, v in KEYS.items():
            db.session.add(SystemConfig(key=k, value=v))
        db.session.commit()
    yield
    with app.app_context():
        SystemConfig.query.filter(SystemConfig.key.in_(list(KEYS))).delete(synchronize_session=False)
        db.session.commit()


def test_count_matches_walking_the_rows(app, seeded):
    with app.app_context():
        before = enc.count_master_key_values()
        assert before == _walk()
        assert before[0] >= 2 and before[1] >= 2


def test_count_takes_few_queries(app, seeded):
    statements = []

    def spy(conn, cursor, statement, *a):
        statements.append(statement)

    with app.app_context():
        engine = db.engine
        event.listen(engine, 'before_cursor_execute', spy)
        try:
            enc.count_master_key_values()
        finally:
            event.remove(engine, 'before_cursor_execute', spy)
    assert len(statements) <= 4, statements
