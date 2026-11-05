"""Failed scheduled renewals slow to one a day and say so."""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from models import WebhookDelivery, db
from models.acme_client_account import AcmeClientAccount
from models.acme_models import AcmeClientOrder
from services import acme_renewal_service as renew_mod
from services.scheduler_service import SchedulerService
from services.webhook_service import WebhookEndpoint, WebhookService
from utils.datetime_utils import utc_now

EVENT = 'acme_order.renewal_failed'


@pytest.fixture
def make(app):
    """Build orders and accounts inside an app context; everything made is removed after."""
    made = {'orders': [], 'accounts': [], 'endpoints': []}

    def order(**fields):
        values = dict(domains=json.dumps([f'{uuid.uuid4().hex[:8]}.example.com']), environment='production',
                      challenge_type='dns-01', status='issued', renewal_enabled=True, key_type='EC-P256')
        values.update(fields)
        row = AcmeClientOrder(**values)
        db.session.add(row)
        db.session.commit()
        made['orders'].append(row.id)
        return row

    def account(**fields):
        values = dict(directory_url='https://ca.example/dir', label=f'renewal-failures-{uuid.uuid4().hex[:8]}',
                      account_url=f'https://ca.example/acct/{uuid.uuid4().hex[:8]}', account_key='k',
                      email='renewal@example.com')
        values.update(fields)
        row = AcmeClientAccount(**values)
        db.session.add(row)
        db.session.commit()
        made['accounts'].append(row.id)
        return row

    def endpoint():
        row = WebhookEndpoint(name=f'renewal-failed-{uuid.uuid4().hex[:8]}', url='https://hooks.example/x',
                              events=json.dumps([EVENT]), enabled=True)
        db.session.add(row)
        db.session.commit()
        made['endpoints'].append(row.id)
        return row

    with app.app_context():
        yield type('Make', (), {'order': staticmethod(order), 'account': staticmethod(account),
                                'endpoint': staticmethod(endpoint)})
        db.session.rollback()
        WebhookDelivery.query.filter(WebhookDelivery.endpoint_id.in_(made['endpoints'])).delete(
            synchronize_session=False)
        WebhookEndpoint.query.filter(WebhookEndpoint.id.in_(made['endpoints'])).delete(synchronize_session=False)
        AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(made['orders'])).delete(synchronize_session=False)
        AcmeClientAccount.query.filter(AcmeClientAccount.id.in_(made['accounts'])).delete(
            synchronize_session=False)
        db.session.commit()


def _pass(order_id, renew=None):
    """One scheduler pass that only considers ``order_id``; returns (attempted ids, outcome)."""
    attempted = []

    def fake_renew(order, **_kw):
        attempted.append(order.id)
        if renew:
            renew(order)

    with patch.object(renew_mod, 'renew_certificate', side_effect=fake_renew), \
            patch.object(renew_mod, '_order_is_due', side_effect=lambda o, *a: o.id == order_id):
        outcome = renew_mod.scheduled_acme_renewal()
    return attempted, outcome


def _fails(_order):
    raise RuntimeError('CA unreachable')


@pytest.mark.parametrize('failures, hours_ago, attempted', [
    (4, 1, True),     # below the threshold: every pass, as before
    (5, 1, False),    # past it: not again the same day
    (5, 23, False),
    (5, 25, True),    # but never stopped for good
    (40, 25, True),
    (5, None, True),
])
def test_past_the_threshold_an_order_is_tried_once_a_day(make, failures, hours_ago, attempted):
    last = utc_now() - timedelta(hours=hours_ago) if hours_ago is not None else None
    order = make.order(renewal_failures=failures, last_error_at=last)
    ids, _ = _pass(order.id)
    assert (order.id in ids) is attempted


def test_each_failure_is_counted_and_announced(make):
    endpoint = make.endpoint()
    order = make.order(renewal_failures=4)
    _pass(order.id, renew=_fails)
    order = db.session.get(AcmeClientOrder, order.id)
    assert order.renewal_failures == 5 and order.error_message == 'CA unreachable'
    assert order.last_error_at is not None
    delivery = WebhookDelivery.query.filter_by(endpoint_id=endpoint.id, event_type=EVENT).one()
    payload = json.loads(delivery.payload)
    assert payload['order']['id'] == order.id
    assert payload['renewal_failures'] == 5 and payload['error'] == 'CA unreachable'
    assert payload['retry_daily'] is True


def test_the_event_says_when_the_rhythm_is_unchanged(make):
    endpoint = make.endpoint()
    order = make.order(renewal_failures=0)
    _pass(order.id, renew=_fails)
    payload = json.loads(WebhookDelivery.query.filter_by(endpoint_id=endpoint.id).one().payload)
    assert payload['renewal_failures'] == 1 and payload['retry_daily'] is False


def test_the_event_can_be_subscribed_to():
    assert EVENT in WebhookService.ALL_EVENTS


def test_the_api_exposes_the_failures(make):
    when = utc_now() - timedelta(hours=2)
    data = make.order(renewal_failures=6, last_error_at=when, error_message='refused').to_dict()
    assert data['renewal_failures'] == 6 and data['renewal_retry_daily'] is True
    assert data['last_error_at'].startswith(when.isoformat()[:19]) and data['error_message'] == 'refused'
    assert make.order().to_dict()['renewal_retry_daily'] is False


def test_a_pass_with_a_failure_is_a_warning(make):
    order = make.order()
    _ids, outcome = _pass(order.id, renew=_fails)
    assert outcome['status'] == 'warning' and '1 renewal(s) failed' in outcome['reason']


def test_an_order_on_the_daily_rhythm_keeps_the_task_in_warning(make):
    order = make.order(renewal_failures=7, last_error_at=utc_now() - timedelta(hours=1))
    ids, outcome = _pass(order.id)
    assert order.id not in ids
    assert outcome['status'] == 'warning' and 'once a day' in outcome['reason']


def test_the_scheduler_records_a_warning(app):
    scheduler = SchedulerService()
    scheduler.register_task('warns', lambda: {'status': 'warning', 'reason': '2 renewal(s) failed'}, 60)
    status = scheduler.run_task_now('warns')
    assert status['last_status'] == 'warning' and status['last_reason'] == '2 renewal(s) failed'
    assert status['last_error'] is None


def test_the_scheduler_page_counts_a_warning(app, auth_client):
    from services import scheduler_service
    scheduler = SchedulerService()
    scheduler.register_task('warns', lambda: {'status': 'warning', 'reason': 'x'}, 60)
    scheduler.run_task_now('warns')
    with patch.object(scheduler_service, '_scheduler', scheduler):
        data = auth_client.get('/api/v2/system/scheduler').get_json()['data']
    assert data['warnings'] == 1
