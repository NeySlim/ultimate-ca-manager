"""Failed scheduled renewals slow to one a day and say so; an order whose CA account is gone
is not renewed under another, and that account cannot be deleted while orders renew through it."""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch
from tests.seeded_rows import delete_client_accounts

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
        if row.challenges_data is None:
            row.set_challenges_dict({'x.example.com': {'token': 'secret-token', 'dns_txt_value': 'txt'}})
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
        delete_client_accounts(AcmeClientAccount.query.filter(AcmeClientAccount.id.in_(made['accounts'])), synchronize_session=False)
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
    assert 'challenges' not in payload['order']  # tokens and TXT values stay out of webhooks


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


# --- the order's CA account -------------------------------------------------

def test_an_order_whose_account_was_deleted_is_not_renewed_elsewhere(make):
    gone = make.order(account_url='https://ca.example/acct/deleted')
    accounts = AcmeClientAccount.query.count()
    with pytest.raises(renew_mod.RenewalBlocked, match='no longer exists'):
        renew_mod.renew_certificate(gone)
    assert AcmeClientAccount.query.count() == accounts  # no placeholder account either


@pytest.mark.sqlite_only(reason='an id naming no account row is refused by the foreign key')
def test_an_order_pinned_to_a_missing_account_row_is_blocked(make):
    order = make.order(acme_client_account_id=987654321)
    with pytest.raises(renew_mod.RenewalBlocked, match='no longer exists'):
        renew_mod.renewal_client(order)


def test_an_order_that_names_no_account_still_resolves(make):
    # Older than per-order accounts: resolved by environment, as before
    order = make.order()
    with patch.object(renew_mod.AcmeClientService, 'for_order', return_value='client') as for_order:
        assert renew_mod.renewal_client(order) == 'client'
    for_order.assert_called_once()


def test_an_order_found_by_its_account_url_still_resolves(make):
    account = make.account()
    order = make.order(account_url=account.account_url)
    assert renew_mod.renewal_client(order).account.id == account.id


def test_the_renewal_window_lookup_creates_no_account(make):
    order = make.order(account_url='https://ca.example/acct/deleted')
    accounts = AcmeClientAccount.query.count()
    with pytest.raises(renew_mod.RenewalBlocked):
        renew_mod._cached_renewal_info(order, type('Cert', (), {'id': -1})(), utc_now())
    assert AcmeClientAccount.query.count() == accounts


def test_an_account_orders_renew_through_cannot_be_deleted(make, auth_client):
    account = make.account()
    pinned = make.order(acme_client_account_id=account.id)
    legacy = make.order(account_url=account.account_url)  # no id column, found by its URL
    r = auth_client.delete(f'/api/v2/acme/client/accounts/{account.id}')
    assert r.status_code == 409
    message = r.get_json()['message']
    assert '2 issued order(s)' in message
    assert pinned.primary_domain in message and legacy.primary_domain in message
    db.session.expire_all()
    assert db.session.get(AcmeClientAccount, account.id) is not None
    assert db.session.get(AcmeClientOrder, pinned.id).acme_client_account_id == account.id


def test_the_message_lists_five_domains_and_counts_the_rest(make, auth_client):
    account = make.account()
    for _ in range(7):
        make.order(acme_client_account_id=account.id)
    message = auth_client.delete(f'/api/v2/acme/client/accounts/{account.id}').get_json()['message']
    assert '7 issued order(s)' in message and 'and 2 more' in message


@pytest.mark.parametrize('fields', [
    {'renewal_enabled': False},
    {'status': 'pending'},
])
def test_an_account_no_issued_renewal_needs_can_go(make, auth_client, fields):
    account = make.account()
    order = make.order(acme_client_account_id=account.id, **fields)
    assert auth_client.delete(f'/api/v2/acme/client/accounts/{account.id}').status_code == 200
    db.session.expire_all()
    assert db.session.get(AcmeClientOrder, order.id).acme_client_account_id is None


def test_an_order_pinned_elsewhere_does_not_hold_an_account_of_the_same_url(make, auth_client):
    # Two rows may share an account URL: an order pinned to the other one does not block this one
    other = make.account()
    account = make.account(account_url=other.account_url)
    make.order(acme_client_account_id=other.id, account_url=other.account_url)
    assert auth_client.delete(f'/api/v2/acme/client/accounts/{account.id}').status_code == 200


def test_deactivation_is_refused_before_the_ca_is_told(make, auth_client):
    account = make.account()
    make.order(acme_client_account_id=account.id)
    with patch('services.acme.acme_client_service.AcmeClientService.deactivate_account') as deactivate:
        r = auth_client.post(f'/api/v2/acme/client/accounts/{account.id}/deactivate',
                             data='{}', content_type='application/json')
    assert r.status_code == 409 and 'renew through it' in r.get_json()['message']
    deactivate.assert_not_called()


def test_deactivation_counts_a_twin_row_of_the_same_account(make, auth_client):
    # The CA knows one account: deactivating it through a twin row kills the other's renewals
    other = make.account()
    twin = make.account(account_url=other.account_url)
    make.order(acme_client_account_id=other.id, account_url=other.account_url)
    with patch('services.acme.acme_client_service.AcmeClientService.deactivate_account') as deactivate:
        r = auth_client.post(f'/api/v2/acme/client/accounts/{twin.id}/deactivate',
                             data='{}', content_type='application/json')
    assert r.status_code == 409 and r.get_json()['message'].startswith('Cannot deactivate')
    deactivate.assert_not_called()


def test_the_refusal_names_the_action_and_the_way_out(make, auth_client):
    account = make.account()
    make.order(acme_client_account_id=account.id)
    message = auth_client.delete(f'/api/v2/acme/client/accounts/{account.id}').get_json()['message']
    assert message.startswith('Cannot delete') and 'Turn off their automatic renewal' in message


# --- per-order renewal switch -------------------------------------------------

def _patch(client, order_id, body):
    return client.patch(f'/api/v2/acme/client/orders/{order_id}', data=json.dumps(body),
                        content_type='application/json')


def test_turning_renewal_off_frees_the_account(make, auth_client):
    account = make.account()
    order = make.order(acme_client_account_id=account.id)
    r = _patch(auth_client, order.id, {'renewal_enabled': False})
    assert r.status_code == 200 and r.get_json()['data']['renewal_enabled'] is False
    db.session.expire_all()
    assert db.session.get(AcmeClientOrder, order.id).renewal_enabled is False
    assert auth_client.delete(f'/api/v2/acme/client/accounts/{account.id}').status_code == 200
    assert _patch(auth_client, order.id, {'renewal_enabled': True}).status_code == 200
    db.session.expire_all()
    assert db.session.get(AcmeClientOrder, order.id).renewal_enabled is True


@pytest.mark.parametrize('body', [{'renewal_enabled': 'false'}, {'renewal_enabled': 0}, {},
                                  {'renewal_enabled': False, 'status': 'pending'}, ['renewal_enabled']])
def test_the_switch_takes_a_strict_boolean_only(make, auth_client, body):
    order = make.order()
    assert _patch(auth_client, order.id, body).status_code == 400
    db.session.expire_all()
    assert db.session.get(AcmeClientOrder, order.id).renewal_enabled is True


def test_the_switch_is_refused_on_an_order_a_renewal_opened(make, auth_client):
    parent = make.order()
    child = make.order(status='ready', renewal_enabled=False, renewal_of_order_id=parent.id)
    r = _patch(auth_client, child.id, {'renewal_enabled': True})
    assert r.status_code == 409 and str(parent.id) in r.get_json()['message']
    db.session.expire_all()
    assert db.session.get(AcmeClientOrder, child.id).renewal_enabled is False


def test_the_switch_is_refused_on_a_proxy_order(make, auth_client):
    order = make.order(is_proxy_order=True)
    assert _patch(auth_client, order.id, {'renewal_enabled': False}).status_code == 409


# --- orders whose account is gone, outside renewal --------------------------

def test_deleting_an_order_whose_account_is_gone_creates_no_account(make, auth_client):
    from models import DnsProvider
    provider = DnsProvider(name=f'gone-{uuid.uuid4().hex[:8]}', provider_type='manual', credentials='{}')
    db.session.add(provider)
    db.session.commit()
    try:
        order = make.order(account_url='https://ca.example/acct/deleted', dns_provider_id=provider.id)
        accounts = AcmeClientAccount.query.count()
        assert auth_client.delete(f'/api/v2/acme/client/orders/{order.id}').status_code == 200
        assert AcmeClientAccount.query.count() == accounts
    finally:
        db.session.delete(db.session.get(DnsProvider, provider.id))
        db.session.commit()


@pytest.mark.parametrize('method, suffix', [('get', 'status'), ('post', 'finalize'), ('post', 'verify')])
def test_acting_on_an_order_whose_account_is_gone_says_so(make, auth_client, method, suffix):
    order = make.order(status='pending', account_url='https://ca.example/acct/deleted')
    accounts = AcmeClientAccount.query.count()
    kwargs = {} if method == 'get' else {'data': '{}', 'content_type': 'application/json'}
    r = getattr(auth_client, method)(f'/api/v2/acme/client/orders/{order.id}/{suffix}', **kwargs)
    assert r.status_code == 409 and 'no longer exists' in r.get_json()['message']
    assert AcmeClientAccount.query.count() == accounts


def test_auto_poll_of_an_order_whose_account_is_gone_stops_with_the_reason(make, app):
    from api.v2.acme_client.orders import _run_auto_poll_background
    order = make.order(status='processing', account_url='https://ca.example/acct/deleted')
    accounts = AcmeClientAccount.query.count()
    with app.test_request_context():
        _run_auto_poll_background(order.id, 'production')
    db.session.expire_all()
    order = db.session.get(AcmeClientOrder, order.id)
    assert order.status == 'pending' and 'no longer exists' in order.error_message
    assert AcmeClientAccount.query.count() == accounts


# --- what the scheduler is told ----------------------------------------------

@pytest.fixture
def renewal_switch(app):
    key = 'acme.client.renewal_enabled'
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=key).first()
    saved = row.value if row else None
    if row is None:
        row = SystemConfig(key=key, value='true')
        db.session.add(row)
    yield row
    row = SystemConfig.query.filter_by(key=key).first()
    if saved is None:
        db.session.delete(row)
    else:
        row.value = saved
    db.session.commit()


def test_a_pass_with_renewal_turned_off_is_skipped(make, renewal_switch):
    renewal_switch.value = 'false'
    db.session.commit()
    outcome = renew_mod.scheduled_acme_renewal()
    assert outcome == {'status': 'skipped', 'reason': 'acme_renewal_off'}


def test_a_pass_that_breaks_is_failed(make):
    with patch.object(renew_mod, '_configured_renewal_days', side_effect=RuntimeError('database gone')):
        outcome = renew_mod.scheduled_acme_renewal()
    assert outcome == {'status': 'failed', 'reason': 'database gone'}


def test_metrics_show_a_warning(app):
    from services import metrics_service, scheduler_service
    scheduler = SchedulerService()
    scheduler.register_task('warns', lambda: {'status': 'warning', 'reason': 'x'}, 60)
    scheduler.register_task('fine', lambda: None, 60)
    scheduler.run_task_now('warns')
    scheduler.run_task_now('fine')
    with patch.object(scheduler_service, '_scheduler', scheduler):
        out = metrics_service.render_metrics()
    assert 'ucm_scheduler_task_warning{task="warns"} 1' in out
    assert 'ucm_scheduler_task_warning{task="fine"} 0' in out
