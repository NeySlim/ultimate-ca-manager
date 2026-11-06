"""Opt-in PostgreSQL mode of the session `app` (UCM_TEST_APP_PG_URL).

Each process (sequential run or xdist worker) owns one schema, ucm_app_<pid>,
reached through the URL's search_path, created empty and dropped at the end.
"""
import atexit
import os

APP_PG_URL = os.environ.get('UCM_TEST_APP_PG_URL', '')
ENABLED = bool(APP_PG_URL)
SCHEMA = f'ucm_app_{os.getpid()}'

# Held open for the whole session: its application_name marks the schema as alive.
_marker = []


def app_url():
    """The URL the application and the migration runner use."""
    separator = '&' if '?' in APP_PG_URL else '?'
    # A lock wait the process itself holds would hang the run: it fails instead.
    return (f'{APP_PG_URL}{separator}options=-csearch_path%3D{SCHEMA}%20-clock_timeout%3D30s'
            f'&application_name={SCHEMA}')


def _connect():
    import psycopg2

    conn = psycopg2.connect(APP_PG_URL, application_name=f'{SCHEMA}_admin')
    conn.autocommit = True
    return conn


def _sweep_abandoned(cur):
    """Drop the schemas of runs that were killed: no session holds their name."""
    cur.execute("""
        SELECT n.nspname FROM pg_namespace n
        WHERE n.nspname LIKE 'ucm\\_app\\_%'
          AND pg_get_userbyid(n.nspowner) = current_user
          AND NOT EXISTS (SELECT 1 FROM pg_stat_activity a
                          WHERE a.application_name IN (n.nspname, n.nspname || '_admin'))
    """)
    for (name,) in cur.fetchall():
        cur.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')


def create_schema():
    conn = _connect()
    _marker.append(conn)
    cur = conn.cursor()
    _sweep_abandoned(cur)
    cur.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
    cur.execute(f'CREATE SCHEMA "{SCHEMA}"')
    atexit.register(drop_schema)


def drop_schema():
    if not _marker:
        return
    conn = _marker.pop()
    try:
        cur = conn.cursor()
        # A session left idle in a transaction would block the DROP forever.
        cur.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                    'WHERE application_name = %s AND pid <> pg_backend_pid()', (SCHEMA,))
        cur.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
    finally:
        conn.close()
