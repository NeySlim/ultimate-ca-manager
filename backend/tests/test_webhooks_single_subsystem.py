"""One webhook subsystem, and the settings-stored one is migrated into it.

UCM carried two. ``/api/v2/settings/webhooks`` kept its entries as a JSON
blob in ``system_config['webhooks']``; no delivery path, no scheduler task
and no frontend screen ever read that blob back. It answered 201 Created,
wrote an audit entry, and dropped every event the operator subscribed to.
``/api/v2/webhooks`` writes ``webhook_endpoints`` rows, which is what the
event bus fans out to.

The settings-backed routes are gone. Migration 087 moves anything an
operator configured through them into ``webhook_endpoints``, so those
subscriptions start being delivered rather than silently disappearing.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from models import SystemConfig, db
from models.webhook_delivery import WebhookDelivery
from services.webhook_service import WebhookEndpoint

LEGACY_ROUTES = (
    ('get', '/api/v2/settings/webhooks'),
    ('post', '/api/v2/settings/webhooks'),
    ('delete', '/api/v2/settings/webhooks/1'),
    ('post', '/api/v2/settings/webhooks/1/test'),
)


class TestLegacyRoutesAreGone:
    def test_no_rule_is_registered_for_them(self, app):
        """Checked on the URL map: the SPA catch-all answers 404/405 for any
        unknown path, so a status code alone would not prove the routes are
        gone."""
        rules = [str(r) for r in app.url_map.iter_rules()
                 if str(r).startswith('/api/v2/settings/webhooks')]
        assert rules == [], f'settings webhook routes still registered: {rules}'

    def test_they_no_longer_answer(self, auth_client):
        for method, path in LEGACY_ROUTES:
            call = getattr(auth_client, method)
            r = call(path, data='{}', content_type='application/json') \
                if method in ('post', 'put') else call(path)
            assert r.status_code in (404, 405), (
                f'{method.upper()} {path} still answers {r.status_code}')

    def test_no_module_writes_the_settings_blob(self):
        """Nothing may start writing system_config['webhooks'] again."""
        import pathlib

        backend = pathlib.Path(__file__).resolve().parent.parent
        offenders = []
        for path in backend.rglob('*.py'):
            if 'tests' in path.parts or 'migrations' in path.parts:
                continue
            text = path.read_text()
            if "key='webhooks'" in text or 'key="webhooks"' in text:
                offenders.append(str(path.relative_to(backend)))
        assert not offenders, f'settings-stored webhooks are back in {offenders}'


class TestTheSurvivingSubsystemDelivers:
    def test_endpoint_receives_a_delivery(self, app, auth_client):
        r = auth_client.post(
            '/api/v2/webhooks',
            data=json.dumps({'name': 'kept', 'url': 'https://hook.example.com/kept',
                             'events': ['certificate.issued']}),
            content_type='application/json')
        assert r.status_code == 201, r.get_data(as_text=True)
        endpoint_id = r.get_json()['data']['id']

        with app.app_context():
            before = WebhookDelivery.query.filter_by(endpoint_id=endpoint_id).count()
            from services.webhook_service import emit_cert_issued
            emit_cert_issued({'refid': 'x', 'descr': 'x'}, actor='test')
            after = WebhookDelivery.query.filter_by(endpoint_id=endpoint_id).count()
        assert after == before + 1


class TestMigration087Parsing:
    """The parsing both backends share, exercised without a database.

    ``_upgrade_sqlite`` and ``_upgrade_pg`` differ only in their SQL dialect;
    every decision about what is worth migrating is taken in ``_entries``, so
    testing it covers the PostgreSQL path too.
    """

    @staticmethod
    def _entries(raw):
        import importlib.util
        import pathlib

        path = (pathlib.Path(__file__).resolve().parent.parent
                / 'migrations' / '087_webhooks_from_settings.py')
        spec = importlib.util.spec_from_file_location('m087p', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module._entries(raw)

    def test_well_formed_entry(self):
        rows = self._entries(json.dumps([
            {'name': 'a', 'url': 'https://h.example/1',
             'events': ['certificate.issued'], 'enabled': True}]))
        assert rows == [{'name': 'a', 'url': 'https://h.example/1',
                         'events': '["certificate.issued"]', 'enabled': True}]

    def test_enabled_defaults_to_true(self):
        rows = self._entries(json.dumps([{'name': 'a', 'url': 'https://h.example/1'}]))
        assert rows[0]['enabled'] is True
        assert rows[0]['events'] == '[]'

    @pytest.mark.parametrize('raw', [
        None, '', 'not json', '{}', '[]', '[1, 2]', '"a string"',
        json.dumps([{'name': '', 'url': 'https://h.example'}]),
        json.dumps([{'name': 'a', 'url': ''}]),
        json.dumps([{'name': '   ', 'url': '   '}]),
    ])
    def test_nothing_usable_yields_nothing(self, raw):
        assert self._entries(raw) == []

    def test_events_that_are_not_a_list_become_empty(self):
        rows = self._entries(json.dumps([
            {'name': 'a', 'url': 'https://h.example/1', 'events': 'oops'}]))
        assert rows[0]['events'] == '[]'

    def test_overlong_values_are_truncated_to_the_columns(self):
        rows = self._entries(json.dumps([
            {'name': 'n' * 300, 'url': 'https://h.example/' + 'u' * 900}]))
        assert len(rows[0]['name']) == 100
        assert len(rows[0]['url']) == 500


@pytest.mark.sqlite_only(reason='runs the migration on the raw sqlite3 connection of the session')
class TestMigration087:
    """The blob an upgrading install still holds is carried over."""

    @staticmethod
    def _run(conn):
        import importlib.util
        import pathlib

        path = (pathlib.Path(__file__).resolve().parent.parent
                / 'migrations' / '087_webhooks_from_settings.py')
        spec = importlib.util.spec_from_file_location('m087', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.upgrade(conn)

    @pytest.fixture
    def legacy_blob(self, app):
        with app.app_context():
            SystemConfig.query.filter_by(key='webhooks').delete()
            WebhookEndpoint.query.filter(
                WebhookEndpoint.url.like('https://hook.example.com/migrated%')).delete(
                    synchronize_session=False)
            db.session.add(SystemConfig(key='webhooks', value=json.dumps([
                {'id': 1, 'name': 'moved', 'url': 'https://hook.example.com/migrated',
                 'events': ['certificate.issued'], 'enabled': True},
                {'id': 2, 'name': 'moved-off',
                 'url': 'https://hook.example.com/migrated-off',
                 'events': ['certificate.revoked'], 'enabled': False},
                {'id': 3, 'name': '', 'url': '', 'events': []},
            ])))
            db.session.commit()
        yield
        with app.app_context():
            SystemConfig.query.filter_by(key='webhooks').delete()
            db.session.commit()

    def _raw(self, app):
        """The migration runner hands migrations a plain DBAPI connection.

        Taken from the engine's own pool rather than opened on the file, so
        the migration and the assertions below see the same database (the
        suite runs SQLite on a StaticPool).
        """
        with app.app_context():
            assert db.engine.url.drivername.startswith('sqlite'), 'SQLite path only'
            raw = db.engine.raw_connection()
            conn = raw.driver_connection
            assert isinstance(conn, sqlite3.Connection)
            return raw, conn

    def test_entries_become_endpoints(self, app, legacy_blob):
        raw, conn = self._raw(app)
        try:
            self._run(conn)
        finally:
            raw.close()

        with app.app_context():
            moved = WebhookEndpoint.query.filter_by(
                url='https://hook.example.com/migrated').first()
            assert moved is not None, 'the settings entry was not carried over'
            assert moved.name == 'moved'
            assert moved.get_events() == ['certificate.issued']
            assert moved.enabled is True
            assert moved.auth_type == 'none'

            off = WebhookEndpoint.query.filter_by(
                url='https://hook.example.com/migrated-off').first()
            assert off is not None
            assert off.enabled is False

            # The nameless/urlless entry is not a webhook; it is dropped.
            assert WebhookEndpoint.query.filter_by(name='').count() == 0

            # The blob is consumed, so the move happens once.
            assert SystemConfig.query.filter_by(key='webhooks').first() is None

    def test_rerun_does_not_duplicate(self, app, legacy_blob):
        raw, conn = self._raw(app)
        try:
            self._run(conn)
            self._run(conn)
        finally:
            raw.close()

        with app.app_context():
            assert WebhookEndpoint.query.filter_by(
                url='https://hook.example.com/migrated').count() == 1

    def test_migrated_endpoint_actually_delivers(self, app, legacy_blob):
        """The point of the move: those events stop being dropped."""
        raw, conn = self._raw(app)
        try:
            self._run(conn)
        finally:
            raw.close()

        with app.app_context():
            moved = WebhookEndpoint.query.filter_by(
                url='https://hook.example.com/migrated').first()
            before = WebhookDelivery.query.filter_by(endpoint_id=moved.id).count()
            from services.webhook_service import emit_cert_issued
            emit_cert_issued({'refid': 'y', 'descr': 'y'}, actor='test')
            after = WebhookDelivery.query.filter_by(endpoint_id=moved.id).count()
        assert after == before + 1, (
            'the migrated subscription still delivers nothing')

    def test_no_blob_is_a_no_op(self, app):
        with app.app_context():
            SystemConfig.query.filter_by(key='webhooks').delete()
            db.session.commit()
        raw, conn = self._raw(app)
        try:
            self._run(conn)
        finally:
            raw.close()

    def test_a_corrupt_blob_is_survived(self, app):
        with app.app_context():
            SystemConfig.query.filter_by(key='webhooks').delete()
            db.session.add(SystemConfig(key='webhooks', value='not json at all'))
            db.session.commit()
        raw, conn = self._raw(app)
        try:
            self._run(conn)
        finally:
            raw.close()
        with app.app_context():
            assert SystemConfig.query.filter_by(key='webhooks').first() is None
