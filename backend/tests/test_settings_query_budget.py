"""The settings and report-schedule readers load their keys in one query, not one per key."""
import json

import pytest
from sqlalchemy import event

from models import db


def _count(app, fn):
    statements = []

    def spy(conn, cursor, statement, *a):
        statements.append(statement)

    engine = db.engine
    event.listen(engine, 'before_cursor_execute', spy)
    try:
        with app.test_request_context('/'):
            result = fn()
    finally:
        event.remove(engine, 'before_cursor_execute', spy)
    return result, statements


def test_general_settings_read_in_few_queries(app):
    view = app.view_functions['settings_v2.get_general_settings'].__wrapped__
    with app.app_context():
        response, statements = _count(app, view)
    assert len(statements) <= 2, f'{len(statements)} queries'


@pytest.fixture
def leftover_settings(app):
    from models import SystemConfig
    with app.app_context():
        for k, v in (('max_login_attempts', '3'), ('session_timeout', '99')):
            if not SystemConfig.query.filter_by(key=k).first():
                db.session.add(SystemConfig(key=k, value=v))
        db.session.commit()


def test_general_settings_values_are_unchanged_by_the_batch(app, auth_client, leftover_settings):
    # stored values come back through the batched read, even over rows another test left
    from models import SystemConfig
    keys = ('max_login_attempts', 'session_timeout')
    with app.app_context():
        saved = {r.key: r.value for r in SystemConfig.query.filter(SystemConfig.key.in_(keys))}
        for k, v in (('max_login_attempts', '9'), ('session_timeout', '1234')):
            row = SystemConfig.query.filter_by(key=k).first()
            if row:
                row.value = v
            else:
                db.session.add(SystemConfig(key=k, value=v))
        db.session.commit()
    try:
        data = auth_client.get('/api/v2/settings/general').get_json()['data']
        assert data['max_login_attempts'] == 9 and data['session_timeout'] == 1234
    finally:
        with app.app_context():
            for k in keys:
                row = SystemConfig.query.filter_by(key=k).first()
                if k in saved:
                    row.value = saved[k]
                elif row:
                    db.session.delete(row)
            db.session.commit()


def test_report_schedule_reads_in_one_query(app):
    view = app.view_functions['reports_pro.get_schedule_settings'].__wrapped__
    with app.app_context():
        response, statements = _count(app, view)
    assert len(statements) <= 1, f'{len(statements)} queries'
    response = response[0] if isinstance(response, tuple) else response
    body = json.loads(response.get_data())
    assert 'pdf_executive' in body['data'] and 'expiring_certificates' in body['data']
