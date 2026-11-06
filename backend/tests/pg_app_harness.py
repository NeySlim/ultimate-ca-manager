"""Opt-in PostgreSQL mode of the session `app` (UCM_TEST_APP_PG_URL).

Each process (sequential run or xdist worker) owns one schema,
ucm_app_<pid>_<token>, reached through the URL's search_path, created empty and
dropped at the end; the random token keeps two hosts with the same pid apart.
Any other create_app('testing') gets a schema of its own, <that name>_<n>,
as it gets a fresh in-memory database on SQLite.
"""
import atexit
import os
import secrets

APP_PG_URL = os.environ.get('UCM_TEST_APP_PG_URL', '')
ENABLED = bool(APP_PG_URL)
SCHEMA = f'ucm_app_{os.getpid()}_{secrets.token_hex(3)}'

# Held open for the whole session: its application_name marks the schemas as alive.
_marker = []
_schemas = []
_creating_session_app = []


def app_url(schema=SCHEMA):
    """The URL the application and the migration runner use."""
    separator = '&' if '?' in APP_PG_URL else '?'
    # A lock wait the process itself holds would hang the run: it fails instead.
    return (f'{APP_PG_URL}{separator}options=-csearch_path%3D{schema}%20-clock_timeout%3D30s'
            f'&application_name={schema}')


def _connect():
    import psycopg2

    conn = psycopg2.connect(APP_PG_URL, application_name=f'{SCHEMA}_admin')
    conn.autocommit = True
    return conn


def _sweep_abandoned(cur):
    """Drop the schemas of runs that were killed: no session carries their name."""
    cur.execute("""
        SELECT n.nspname FROM pg_namespace n
        WHERE n.nspname ~ '^ucm_app_[0-9]+_[0-9a-f]{6}(_[0-9]+)?$'
          AND pg_get_userbyid(n.nspowner) = current_user
          AND NOT EXISTS (
              SELECT 1 FROM pg_stat_activity a
              WHERE substring(a.application_name from '^ucm_app_[0-9]+_[0-9a-f]{6}')
                    = substring(n.nspname from '^ucm_app_[0-9]+_[0-9a-f]{6}'))
    """)
    for (name,) in cur.fetchall():
        cur.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')


def _new_schema(cur, name):
    cur.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
    cur.execute(f'CREATE SCHEMA "{name}"')
    _schemas.append(name)


def create_schema():
    conn = _connect()
    _marker.append(conn)
    cur = conn.cursor()
    _sweep_abandoned(cur)
    _new_schema(cur, SCHEMA)
    atexit.register(drop_schema)


def drop_schema():
    if not _marker:
        return
    conn = _marker.pop()
    try:
        cur = conn.cursor()
        # A session left idle in a transaction would block the DROP forever.
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE (application_name = %s OR application_name LIKE %s) "
                    "AND pid <> pg_backend_pid()", (SCHEMA, SCHEMA.replace('_', '\\_') + '\\_%'))
        while _schemas:
            cur.execute(f'DROP SCHEMA IF EXISTS "{_schemas.pop()}" CASCADE')
    finally:
        conn.close()


def session_app(create_app, config_name):
    """create_app() for the session fixture, on the main schema."""
    _creating_session_app.append(True)
    try:
        return create_app(config_name)
    finally:
        _creating_session_app.pop()


def isolating(create_app, testing_config):
    """create_app() that builds every other testing app in a schema of its own."""
    import functools

    from utils.db_url import sqlalchemy_url

    @functools.wraps(create_app)
    def create_isolated_app(config_name=None, *args, **kwargs):
        if _creating_session_app or config_name != 'testing' or not _marker:
            return create_app(config_name, *args, **kwargs)
        schema = f'{SCHEMA}_{len(_schemas)}'
        _new_schema(_marker[0].cursor(), schema)
        saved = testing_config.SQLALCHEMY_DATABASE_URI, os.environ.get('DATABASE_URL')
        testing_config.SQLALCHEMY_DATABASE_URI = sqlalchemy_url(app_url(schema))
        os.environ['DATABASE_URL'] = app_url(schema)
        try:
            return create_app(config_name, *args, **kwargs)
        finally:
            testing_config.SQLALCHEMY_DATABASE_URI, os.environ['DATABASE_URL'] = saved
    return create_isolated_app
