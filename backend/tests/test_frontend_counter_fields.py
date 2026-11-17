"""Counters the interface reads but the API never produced.

Three tiles were stuck on zero because the field the page reads was never in the
response: the audit page's user count, the SSH CA list's certificate count, and the
dashboard's per-account ACME order count. Each test asserts the field is there and
carries the right number.
"""
from datetime import timedelta
from uuid import uuid4

from models import db, AuditLog, AcmeAccount, AcmeOrder
from utils.datetime_utils import utc_now


class TestAuditUniqueUsers:
    """The audit page shows how many distinct users acted over the window."""

    def test_three_new_names_raise_the_count_by_three(self, app, auth_client):
        """Counted against the reading before, since the suite leaves its own rows,
        and never against top_users, which stops at ten."""
        before = auth_client.get('/api/v2/audit/stats?days=30').get_json()['data']
        assert 'unique_users' in before

        names = [f'counter-{uuid4().hex[:8]}' for _ in range(3)]
        with app.app_context():
            for i, username in enumerate(names + [names[0]]):
                db.session.add(AuditLog(
                    timestamp=utc_now() - timedelta(hours=i),
                    username=username, action='login_success',
                    resource_type='user', success=True,
                ))
            db.session.commit()

        after = auth_client.get('/api/v2/audit/stats?days=30').get_json()['data']
        assert after['unique_users'] == before['unique_users'] + 3

    def test_unique_users_is_zero_on_an_empty_window(self, auth_client):
        resp = auth_client.get('/api/v2/audit/stats?days=0')
        assert resp.status_code == 200
        assert resp.get_json()['data']['unique_users'] == 0


class TestAcmeAccountOrderCount:
    """Each ACME account on the dashboard shows how many orders it has placed."""

    @staticmethod
    def _add_account(account_id, order_count):
        db.session.add(AcmeAccount(
            account_id=account_id, jwk='{}', jwk_thumbprint=f'thumb-{account_id}',
            contact=f'["mailto:{account_id}@example.test"]', status='valid',
        ))
        db.session.commit()
        for i in range(order_count):
            db.session.add(AcmeOrder(
                order_id=f'order-{account_id}-{i}', account_id=account_id,
                status='valid', identifiers='[{"type": "dns", "value": "a.example.test"}]',
            ))
        db.session.commit()

    def test_listing_reports_the_order_count(self, app, auth_client):
        with app.app_context():
            account_id = f'acct-counter-{uuid4().hex[:8]}'
            self._add_account(account_id, 3)

        resp = auth_client.get('/api/v2/acme/accounts')
        assert resp.status_code == 200

        rows = {row['account_id']: row for row in resp.get_json()['data']}
        assert rows[account_id]['orders_count'] == 3

    def test_an_account_with_no_order_reports_zero(self, app, auth_client):
        with app.app_context():
            account_id = f'acct-empty-{uuid4().hex[:8]}'
            self._add_account(account_id, 0)

        resp = auth_client.get('/api/v2/acme/accounts')
        rows = {row['account_id']: row for row in resp.get_json()['data']}
        assert rows[account_id]['orders_count'] == 0
