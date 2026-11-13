"""Keep the users id counter above every user id the restored rows still name."""
from sqlalchemy import inspect, text

from models import db
from services.backup.restore.legacy_repairs import highest_named

# Sections whose rows carry raw user ids from the archive's installation
SECTIONS = ('audit_logs', 'approval_requests')


def advance_users_counter() -> None:
    """Replay migration 150's seeding of the users counter inside the restore's transaction."""
    conn = db.session.connection()
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    columns = {}

    def has_column(table, column):
        if table not in tables:
            return False
        if table not in columns:
            columns[table] = {c['name'] for c in inspector.get_columns(table)}
        return column in columns[table]

    seed = highest_named(lambda q: conn.execute(text(q)).scalar(),
                         lambda q: conn.execute(text(q)).fetchall(), has_column)
    if conn.dialect.name == 'sqlite':
        current = conn.execute(text("SELECT seq FROM sqlite_sequence WHERE name = 'users'")).scalar()
        if current is None:
            conn.execute(text("INSERT INTO sqlite_sequence (name, seq) VALUES ('users', :n)"), {'n': seed})
        elif current < seed:
            conn.execute(text("UPDATE sqlite_sequence SET seq = :n WHERE name = 'users'"), {'n': seed})
    elif conn.dialect.name == 'postgresql':
        sequence = conn.execute(text("SELECT pg_get_serial_sequence('users', 'id')")).scalar()
        if sequence:
            current = conn.execute(text("SELECT pg_sequence_last_value(CAST(:s AS regclass))"),
                                   {'s': sequence}).scalar() or 0
            if seed > current:
                conn.execute(text("SELECT setval(CAST(:s AS regclass), :n, true)"),
                             {'s': sequence, 'n': seed})
