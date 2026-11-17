"""An auto-approved authorization outlives the entry that records it.

An admin-configured domain skips challenge validation: the authorization is
created directly in `valid` state and the order moves straight to `ready`.
The entry recording that used to be written before the commit, and
`AuditService.log_action` commits the session it is given and rolls all of it
back when its own entry cannot be written.

Everything the transaction still held went with it. `create_order` stages the
order and flushes it without committing, then loops over the identifiers, so
a failure here took the order down as well and left the authorizations that
had already been committed by an earlier trip round the loop pointing at
nothing. The client was answered with an order URL for a row that no longer
existed.
"""
import pytest

from models import db


@pytest.fixture
def audit_always_fails(monkeypatch):
    from models.audit_log import AuditLog

    def failing_hash(self, *args, **kwargs):
        raise RuntimeError('audit hash chain unavailable')

    monkeypatch.setattr(AuditLog, 'compute_hash', failing_hash, raising=False)


class TestTheOrderSurvivesItsAuditEntry:
    def test_an_unwritable_entry_does_not_take_the_order_with_it(
            self, app, audit_always_fails, monkeypatch):
        from models.acme_models import (AcmeAccount, AcmeOrder,
                                        AcmeAuthorization)
        from services.acme.acme_service import AcmeService

        with app.app_context():
            account = AcmeAccount(
                account_id='acct-auto-approve-order-probe',
                jwk='{}', jwk_thumbprint='auto-approve-probe',
                status='valid', contact='[]')
            db.session.add(account)
            db.session.commit()

            service = AcmeService()
            monkeypatch.setattr(
                type(service), '_is_domain_auto_approved',
                lambda self, domain: True, raising=False)

            order = service.create_order(
                account.account_id,
                [{'type': 'dns', 'value': 'auto-approved.example'},
                 {'type': 'dns', 'value': 'auto-approved-two.example'}])

            assert order is not None, 'no order came back at all'
            stored = AcmeOrder.query.filter_by(
                order_id=order.order_id).first()
            assert stored is not None, (
                'the order the client was handed does not exist: the audit '
                'entry could not be written and took it back down')

            orphans = AcmeAuthorization.query.filter(
                AcmeAuthorization.order_id == order.order_id).all()
            assert orphans, 'the authorizations went too'
            for row in orphans:
                assert AcmeOrder.query.filter_by(
                    order_id=row.order_id).first() is not None, (
                    'an authorization points at an order that is gone')
