"""/guide/<chapter>: the chapter drawn at build time, in the page the server sends.

A browser's reader view decides at load whether a page is an article: the chapter is in the
HTML for a valid session (checked as the API checks it, database sessions included), in the
account's language, else the browser's among the help's, else English. Without a session, for an
unknown chapter, a query or a build without the drawn pages: index.html as before.
"""
import json
import os
import uuid
from datetime import timedelta

import pytest

from api import ui_routes
from models import User, db
from tests.header_guard import guarded
from tests.session_support import pose_signed_in
from utils.datetime_utils import utc_now

PG_URL = os.getenv('UCM_TEST_APP_PG_URL') or os.getenv('UCM_TEST_PG_URL')
PASSWORD = 'Guide-Reader-Pass-1!'
INDEX = ('<!doctype html>\n<html lang="en">\n  <head>\n    <title>UCM - Ultimate Certificate Manager</title>\n'
         '  </head>\n  <body>\n    <div id="root"></div>\n  </body>\n</html>\n')
LANGS = ('en', 'fr', 'ru', 'zh')


def _drawn(lang, chapter):
    return (f'<!doctype html>\n<html lang="{lang}">\n  <head>\n    <title>{chapter} {lang} · Guide · UCM</title>\n'
            f'  </head>\n  <body>\n    <div id="root" data-guide="{lang}/{chapter}"><article>{lang.upper()}-{chapter}</article>'
            '</div>\n  </body>\n</html>\n')


def _write_dist(root, drawn=True):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'index.html').write_text(INDEX, encoding='utf-8')
    # An HTML file beside the drawn pages: a chapter name never reaches it
    (root / 'elsewhere.html').write_text('<p>elsewhere</p>', encoding='utf-8')
    if drawn:
        for lang in LANGS:
            (root / 'guide-prerender' / lang).mkdir(parents=True, exist_ok=True)
            for chapter in ('cas', 'acme'):
                (root / 'guide-prerender' / lang / f'{chapter}.html').write_text(_drawn(lang, chapter), encoding='utf-8')
    return root


@pytest.fixture
def dist(tmp_path, monkeypatch):
    """A build with the drawn chapters (cas and acme in each language of the help)."""
    root = _write_dist(tmp_path / 'dist')
    monkeypatch.setattr(ui_routes, 'FRONTEND_DIR', root)
    return root


def _new_reader(application, **fields):
    with application.app_context():
        user = User(username=f'guide-{uuid.uuid4().hex[:8]}', email=f'{uuid.uuid4().hex[:8]}@example.test',
                    role='viewer', active=True, **fields)
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        return user.id


def _drop_reader(application, user_id):
    from models.user import UserSession
    with application.app_context():
        db.session.rollback()
        UserSession.query.filter_by(user_id=user_id).delete()
        user = db.session.get(User, user_id)
        if user is not None:
            db.session.delete(user)
        db.session.commit()


@pytest.fixture
def reader(app):
    """A viewer account; set(prefs=..., **columns) changes it."""
    user_id = _new_reader(app)

    class Reader:
        id = user_id

        @staticmethod
        def set(prefs=None, **columns):
            with app.app_context():
                user = db.session.get(User, user_id)
                if prefs is not None:
                    user.preferences = json.dumps(prefs)
                for key, value in columns.items():
                    setattr(user, key, value)
                db.session.commit()

    yield Reader
    _drop_reader(app, user_id)


def _signed_in(app, user_id, **extra):
    client = app.test_client()
    with app.app_context():
        user = db.session.get(User, user_id)
        with client.session_transaction() as sess:
            pose_signed_in(sess, user)
            sess.update(extra)
    return client


def _text(r):
    return r.get_data(as_text=True)


def _undrawn(r):
    assert r.status_code == 200
    assert _text(r) == INDEX


def _no_cache_varied(r):
    assert r.headers['Cache-Control'] == 'no-cache, no-store, must-revalidate'
    assert r.headers['Pragma'] == 'no-cache'
    assert r.headers['Expires'] == '0'
    assert {'cookie', 'accept-language'} <= {v.strip().lower() for v in r.headers['Vary'].split(',')}


def test_without_a_session_the_page_is_index_html_as_before(app, dist):
    r = app.test_client().get('/guide/cas', headers={'Accept-Language': 'fr'})
    _undrawn(r)
    _no_cache_varied(r)


def test_a_session_gets_the_chapter_in_the_page_without_cache_and_varied(app, dist, reader):
    r = _signed_in(app, reader.id).get('/guide/cas')
    assert r.status_code == 200
    assert r.mimetype == 'text/html'
    assert _text(r) == _drawn('en', 'cas')
    _no_cache_varied(r)


def test_the_accounts_language_comes_first(app, dist, reader):
    reader.set(prefs={'language': 'fr'})
    r = _signed_in(app, reader.id).get('/guide/acme', headers={'Accept-Language': 'ru'})
    assert _text(r) == _drawn('fr', 'acme')


@pytest.mark.parametrize('chosen', ['de', 'ja', 'pt-BR'])
def test_an_account_language_without_a_help_reads_english(app, dist, reader, chosen):
    reader.set(prefs={'language': chosen})
    r = _signed_in(app, reader.id).get('/guide/cas', headers={'Accept-Language': 'fr'})
    assert _text(r) == _drawn('en', 'cas')


@pytest.mark.parametrize('header, lang', [
    ('ru-RU,ru;q=0.9,en;q=0.5', 'ru'),
    ('zh-CN', 'zh'),
    ('fr-FR,fr;q=0.9', 'fr'),
    # The client reads German, as the browser asks: English help, not the French further down the list
    ('de-DE,de;q=0.9,fr;q=0.4', 'en'),
    ('de-DE,de;q=0.9', 'en'),
    ('', 'en'),
])
def test_without_an_account_language_the_browsers_then_english(app, dist, reader, header, lang):
    r = _signed_in(app, reader.id).get('/guide/cas', headers={'Accept-Language': header} if header else {})
    assert _text(r) == _drawn(lang, 'cas')


def test_the_accounts_theme_is_on_the_page(app, dist, reader):
    reader.set(prefs={'language': 'zh', 'theme_family': 'aurore', 'theme_mode': 'light'})
    page = _text(_signed_in(app, reader.id).get('/guide/cas'))
    assert '<html lang="zh" data-theme="aurore" data-mode="light">' in page
    reader.set(prefs={'theme_family': 'purple', 'theme_mode': 'system'})
    page = _text(_signed_in(app, reader.id).get('/guide/cas'))
    assert '<html lang="en" data-theme="atelier">' in page


@pytest.mark.parametrize('path', [
    '/guide/nothing', '/guide/cas/more', '/guide/..%2f..%2felsewhere', '/guide/%2e%2e%2f%2e%2e%2felsewhere',
    '/guide/%2e%2e', '/guide', '/guide/',
    '/guide/cas?print=all', '/guide/cas?q=crl', '/guide?print=all',
])
def test_an_unknown_chapter_or_a_query_gets_index_html(app, dist, reader, path):
    r = _signed_in(app, reader.id).get(path)
    _undrawn(r)
    _no_cache_varied(r)


def test_a_build_without_the_drawn_chapters_gets_index_html(app, tmp_path, monkeypatch, reader):
    monkeypatch.setattr(ui_routes, 'FRONTEND_DIR', _write_dist(tmp_path / 'bare', drawn=False))
    _undrawn(_signed_in(app, reader.id).get('/guide/cas'))


def test_a_language_whose_page_is_missing_gets_index_html(app, dist, reader):
    (dist / 'guide-prerender' / 'ru' / 'cas.html').unlink()
    reader.set(prefs={'language': 'ru'})
    _undrawn(_signed_in(app, reader.id).get('/guide/cas'))


def test_the_drawn_pages_are_never_served_as_files(app, dist, reader):
    for path in ('/guide-prerender/fr/cas.html', '/guide-prerender/en/acme.html', '/guide-prerender',
                 '/./guide-prerender/en/cas.html', '/assets/../guide-prerender/en/cas.html', '/%2e/guide-prerender/fr/cas.html'):
        _undrawn(_signed_in(app, reader.id).get(path))


def test_a_session_past_its_inactivity_timeout_gets_index_html(app, dist, reader):
    stale = (utc_now() - timedelta(days=30)).isoformat()
    _undrawn(_signed_in(app, reader.id, last_activity=stale).get('/guide/cas'))


def test_a_session_closed_by_a_credential_change_gets_index_html(app, dist, reader):
    client = _signed_in(app, reader.id)
    reader.set(session_version=7)
    _undrawn(client.get('/guide/cas'))


def test_a_disabled_account_gets_index_html(app, dist, reader):
    client = _signed_in(app, reader.id)
    reader.set(active=False)
    _undrawn(client.get('/guide/cas'))


def test_a_session_held_by_a_forced_change_gets_index_html(app, dist, reader):
    from auth.twofa_enforcement import ENROLL_SESSION_KEY
    _undrawn(_signed_in(app, reader.id, **{ENROLL_SESSION_KEY: True}).get('/guide/cas'))
    reader.set(force_password_change=True)
    _undrawn(_signed_in(app, reader.id).get('/guide/cas'))


def test_the_reader_is_checked_as_the_api_checks_a_session(app, reader):
    """The route's own check, apart from the middleware that clears a stale session first."""
    from flask import session

    def reader_with(**extra):
        with app.test_request_context('/guide/cas'):
            pose_signed_in(session, db.session.get(User, reader.id))
            session.update(extra)
            found = ui_routes._guide_reader()
            return found.id if found else None

    assert reader_with() == reader.id
    assert reader_with(last_activity=(utc_now() - timedelta(days=30)).isoformat()) is None
    assert reader_with(session_version=99) is None
    reader.set(active=False)
    assert reader_with() is None


def test_a_failing_session_check_gets_index_html(app, dist, reader, monkeypatch):
    def broken():
        raise RuntimeError('database gone')
    monkeypatch.setattr(ui_routes, '_guide_reader', broken)
    _undrawn(_signed_in(app, reader.id).get('/guide/cas'))


# ---- database sessions (HA): the same check, the session opened by a login --------------------

@pytest.fixture(autouse=True)
def _drop_session_table_from_metadata():
    """The SQL store registers flask_sessions on the shared metadata; never leak it."""
    yield
    t = db.metadata.tables.get('flask_sessions')
    if t is not None:
        db.metadata.remove(t)


def _sql_store_app(monkeypatch, url, database_type):
    from config.settings import TestingConfig
    from utils.db_url import sqlalchemy_url
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', sqlalchemy_url(url))
    monkeypatch.setattr(TestingConfig, 'DATABASE_TYPE', database_type)
    monkeypatch.setattr(TestingConfig, 'SESSION_TYPE', 'sqlalchemy')
    monkeypatch.setattr(TestingConfig, 'SESSION_SQLALCHEMY_TABLE', 'flask_sessions', raising=False)
    from app import create_app
    return guarded(create_app('testing'))


def _dispose(*applications):
    for application in applications:
        with application.app_context():
            db.session.remove()
            db.engine.dispose()


@pytest.fixture(params=[
    'sql-sqlite',
    pytest.param('sql-postgresql', marks=[
        pytest.mark.postgres,
        pytest.mark.skipif(not PG_URL, reason='no PostgreSQL URL for the two-node session test')]),
])
def nodes(request, monkeypatch, tmp_path):
    """(node that signs in, node that serves the guide) on one SQL session store."""
    from tests import pg_app_harness
    if request.param == 'sql-sqlite':
        if pg_app_harness.ENABLED:
            pytest.skip('file-database store, not meaningful in PostgreSQL mode')
        node = _sql_store_app(monkeypatch, f'sqlite:///{tmp_path / "guide-sessions.db"}', 'sqlite')
        try:
            yield node, node
        finally:
            _dispose(node)
        return
    import psycopg
    schema = f'ucm_guide_{uuid.uuid4().hex[:8]}'
    admin = psycopg.connect(PG_URL, autocommit=True)
    admin.execute(f'CREATE SCHEMA "{schema}"')
    sep = '&' if '?' in PG_URL else '?'
    url = f'{PG_URL}{sep}options=-csearch_path%3D{schema}'
    monkeypatch.setenv('DATABASE_URL', url)
    # The shared-suite wrapper would give each application its own schema
    pg_app_harness._creating_session_app.append(True)
    created = []
    try:
        created.append(_sql_store_app(monkeypatch, url, 'postgresql'))
        created.append(_sql_store_app(monkeypatch, url, 'postgresql'))
        yield created[0], created[1]
    finally:
        pg_app_harness._creating_session_app.pop()
        _dispose(*created)
        admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin.close()


def test_a_database_session_gets_the_chapter_on_any_node(nodes, dist):
    from sqlalchemy import text
    first, second = nodes
    assert first.config['SESSION_TYPE'] == 'sqlalchemy'
    user_id = _new_reader(first, preferences=json.dumps({'language': 'fr'}))
    try:
        signing, reading = first.test_client(), second.test_client()
        _undrawn(reading.get('/guide/cas'))
        login = signing.post('/api/v2/auth/login/password', json={'username': _username(first, user_id), 'password': PASSWORD})
        assert login.status_code == 200, login.data
        reading.set_cookie('session', signing.get_cookie('session').value)
        assert _text(reading.get('/guide/cas')) == _drawn('fr', 'cas')
        # The row gone (logout elsewhere, cleanup): the page as before
        with second.app_context():
            db.session.execute(text('DELETE FROM flask_sessions'))
            db.session.commit()
        _undrawn(reading.get('/guide/cas'))
    finally:
        _drop_reader(first, user_id)


def _username(application, user_id):
    with application.app_context():
        return db.session.get(User, user_id).username
