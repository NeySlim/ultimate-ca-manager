"""init_db.py names the database it initialised without printing the DATABASE_URL password."""
import os

URL = 'postgresql://ucm:S3cret-Init-Db@db.example:5432/ucmdb'


def test_init_db_prints_the_database_label_not_the_url(app, monkeypatch, capsys):
    # The module sets this at import: restored after the test
    monkeypatch.setenv('UCM_SKIP_SECRET_VALIDATION', os.environ.get('UCM_SKIP_SECRET_VALIDATION', '1'))
    import init_db
    monkeypatch.setattr(init_db, 'create_app', lambda: app)
    monkeypatch.setenv('DATABASE_URL', URL)
    monkeypatch.setitem(app.config, 'SQLALCHEMY_DATABASE_URI', URL)
    init_db.init_database()
    out = capsys.readouterr().out
    assert 'S3cret-Init-Db' not in out
    assert 'Database: PostgreSQL, database ucmdb' in out


def test_init_db_names_the_sqlite_file(app, monkeypatch, capsys):
    monkeypatch.setenv('UCM_SKIP_SECRET_VALIDATION', os.environ.get('UCM_SKIP_SECRET_VALIDATION', '1'))
    import init_db
    monkeypatch.setattr(init_db, 'create_app', lambda: app)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    init_db.init_database()
    assert f"Database: SQLite, {app.config['DATABASE_PATH']}" in capsys.readouterr().out
