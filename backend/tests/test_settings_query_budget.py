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


def test_general_settings_values_are_unchanged_by_the_batch(app, auth_client):
    # stored values come back through the batched read
    from models import SystemConfig
    with app.app_context():
        db.session.add(SystemConfig(key='max_login_attempts', value='9'))
        db.session.add(SystemConfig(key='session_timeout', value='1234'))
        db.session.commit()
    try:
        data = auth_client.get('/api/v2/settings/general').get_json()['data']
        assert data['max_login_attempts'] == 9 and data['session_timeout'] == 1234
    finally:
        with app.app_context():
            SystemConfig.query.filter(SystemConfig.key.in_(['max_login_attempts', 'session_timeout'])).delete(
                synchronize_session=False)
            db.session.commit()


def test_report_schedule_reads_in_one_query(app):
    view = app.view_functions['reports_pro.get_schedule_settings'].__wrapped__
    with app.app_context():
        response, statements = _count(app, view)
    assert len(statements) <= 1, f'{len(statements)} queries'
    response = response[0] if isinstance(response, tuple) else response
    body = json.loads(response.get_data())
    assert 'pdf_executive' in body['data'] and 'expiring_certificates' in body['data']
