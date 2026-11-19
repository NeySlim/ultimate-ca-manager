"""A discovery profile's next scan follows its schedule when the schedule changes."""
import uuid
from datetime import timedelta

import pytest

from models import db
from models.discovered_certificate import ScanProfile
from utils.datetime_utils import utc_now

URL = '/api/v2/discovery/profiles'


@pytest.fixture
def profile(app, auth_client):
    r = auth_client.post(URL, json={
        'name': f'rep24b-{uuid.uuid4().hex[:8]}', 'targets': ['192.0.2.10'],
        'schedule_enabled': True, 'schedule_interval_minutes': 1440})
    assert r.status_code == 201, r.data[:300]
    pid = r.get_json()['data']['id']
    yield pid
    with app.app_context():
        ScanProfile.query.filter_by(id=pid).delete()
        db.session.commit()


def _next(app, pid):
    with app.app_context():
        return db.session.get(ScanProfile, pid).next_scan_at


def _set_next(app, pid, value):
    with app.app_context():
        db.session.get(ScanProfile, pid).next_scan_at = value
        db.session.commit()


def _minutes_from_now(value):
    return (value - utc_now().replace(tzinfo=None)).total_seconds() / 60


def test_a_new_interval_moves_the_next_scan(app, auth_client, profile):
    assert _minutes_from_now(_next(app, profile)) > 1000
    r = auth_client.put(f'{URL}/{profile}', json={'schedule_interval_minutes': 60})
    assert r.status_code == 200, r.data[:300]
    assert 55 <= _minutes_from_now(_next(app, profile)) <= 61


def test_reenabling_does_not_run_on_an_old_date(app, auth_client, profile):
    assert auth_client.put(f'{URL}/{profile}', json={'schedule_enabled': False}).status_code == 200
    _set_next(app, profile, utc_now().replace(tzinfo=None) - timedelta(days=30))
    assert auth_client.put(f'{URL}/{profile}', json={'schedule_enabled': True}).status_code == 200
    assert _minutes_from_now(_next(app, profile)) > 1000


def test_an_update_that_leaves_the_schedule_alone_keeps_the_date(app, auth_client, profile):
    when = utc_now().replace(tzinfo=None) + timedelta(minutes=7)
    _set_next(app, profile, when)
    r = auth_client.put(f'{URL}/{profile}', json={
        'description': 'edited', 'schedule_enabled': True, 'schedule_interval_minutes': 1440})
    assert r.status_code == 200, r.data[:300]
    assert _next(app, profile) == when
