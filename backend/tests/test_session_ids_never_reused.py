"""The session database never hands an id out twice; any other database keeps the product schema.

A file's cleanup deletes its rows; rows elsewhere that name those ids (audit, notifications,
queues, links SQLite does not enforce) must never be read as the next file's rows.
"""
from sqlalchemy import create_engine, text

from models import db
from models.group import Group


def _make(name):
    group = Group(name=name)
    db.session.add(group)
    db.session.commit()
    return group.id


def test_a_deleted_id_is_not_given_again(app):
    with app.app_context():
        first = _make('flk7-ids-first')
        db.session.delete(db.session.get(Group, first))
        db.session.commit()
        second = _make('flk7-ids-second')
        try:
            assert second > first
        finally:
            db.session.delete(db.session.get(Group, second))
            db.session.commit()


def test_another_sqlite_database_keeps_the_declared_schema(app, tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "plain.db"}')
    try:
        Group.__table__.create(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO groups (name) VALUES ('a'), ('b')"))
            conn.execute(text("DELETE FROM groups WHERE name = 'b'"))
            conn.execute(text("INSERT INTO groups (name) VALUES ('c')"))
            # Without AUTOINCREMENT SQLite gives max(rowid) + 1 again, as the product does
            assert conn.execute(text("SELECT id FROM groups WHERE name = 'c'")).scalar() == 2
    finally:
        engine.dispose()
