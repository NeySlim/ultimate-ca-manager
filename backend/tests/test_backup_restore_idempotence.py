"""Restoring an archive twice must leave what restoring it once left.

Approval requests and ACME client orders were created unconditionally, with
no identity to match them against what was already here: a second restore of
the same archive left two copies of every pending approval and of every order
the external CA still knows under one URL. The approvals also came back
without their creation date — the very thing that tells two requests apart —
because an unparsable date was quietly turned into None.

The payloads here are the rows an archive carries, read through the same
exporter a backup uses, and applied through the same plan and the same single
transaction a restore uses. They are filtered to the rows each test created:
the session database is shared, so an archive of the whole table would carry
whatever other files left behind, and this file would pass or fail according
to what ran before it.
"""
import json
from datetime import datetime

import pytest

from models import db
from services.backup.export_generic import IdentityIndex, export_section
from services.backup.restore import (
    RestorePlan, RestoreValidationError, single_transaction)


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _archived(section_name, keep):
    """The rows an archive would carry for a section, as JSON holds them."""
    rows = [row for row in export_section(section_name, IdentityIndex()) if keep(row)]
    return json.loads(json.dumps(rows))


def _restore(payload):
    """Apply a payload the way a restore does: one plan, one transaction."""
    plan = RestorePlan.build(payload)
    results = {}
    service = _service()
    with single_transaction():
        service._restore_approval_requests(payload, results, plan)
        service._restore_acme_client_orders(payload, results, plan)
    return results


CREATED_AT = datetime(2026, 9, 12, 8, 30, 15, 123456)


@pytest.fixture
def pending_approval(app, create_user):
    """A pending approval request, its archive rows, and a clean database.

    The request is exported and then removed, so each test starts from the
    situation a restore is for: an archive holding a row this installation
    does not have.
    """
    from models.policy import ApprovalRequest

    user = create_user(username='backup_idempotence_requester')
    with app.app_context():
        ApprovalRequest.query.filter_by(requester_id=user['id']).delete()
        request = ApprovalRequest(
            request_type='certificate',
            requester_id=user['id'],
            request_data=json.dumps({'cn': 'idempotent-approval.example.test'}),
            requester_comment='waiting for an approver',
            status='pending',
            required_approvals=2,
            created_at=CREATED_AT,
        )
        db.session.add(request)
        db.session.commit()

        payload = {'approval_requests': _archived(
            'approval_requests', lambda row: row['requester_id'] == user['id'])}
        assert len(payload['approval_requests']) == 1

        ApprovalRequest.query.filter_by(requester_id=user['id']).delete()
        db.session.commit()
        try:
            yield user, payload
        finally:
            ApprovalRequest.query.filter_by(requester_id=user['id']).delete()
            db.session.commit()


def _approvals_of(user):
    from models.policy import ApprovalRequest
    return ApprovalRequest.query.filter_by(requester_id=user['id']).all()


class TestApprovalRequestsAreRestoredOnce:
    def test_a_second_restore_does_not_add_a_second_request(self, app, pending_approval):
        user, payload = pending_approval
        with app.app_context():
            _restore(payload)
            first = _approvals_of(user)
            assert len(first) == 1, 'the request was not restored'
            restored_id = first[0].id

            _restore(payload)
            again = _approvals_of(user)
            assert len(again) == 1, \
                'restoring the same archive twice left two pending approvals'
            assert again[0].id == restored_id, \
                'the second restore replaced the row instead of updating it'

    def test_a_restored_request_keeps_its_creation_date(self, app, pending_approval):
        user, payload = pending_approval
        with app.app_context():
            _restore(payload)
            restored = _approvals_of(user)[0]
            assert restored.created_at == CREATED_AT, \
                'the request came back dated from the restore, not from the archive'
            assert restored.required_approvals == 2
            assert restored.status == 'pending'

    def test_an_unparsable_creation_date_stops_the_restore(self, app, pending_approval):
        user, payload = pending_approval
        payload['approval_requests'][0]['created_at'] = 'not-a-date'
        with app.app_context():
            with pytest.raises(RestoreValidationError, match='created_at'):
                _restore(payload)
            assert _approvals_of(user) == [], \
                'a request with an invalid date was restored anyway'

    def test_a_missing_creation_date_stops_the_restore(self, app, pending_approval):
        user, payload = pending_approval
        payload['approval_requests'][0]['created_at'] = None
        with app.app_context():
            with pytest.raises(RestoreValidationError, match='created_at'):
                _restore(payload)
            assert _approvals_of(user) == []


class TestApprovalRequestsFollowTheirCertificate:
    """The number in the archive is the source's; the identity beside it is
    what says which certificate the request was about."""

    def test_the_request_lands_on_the_certificate_of_that_refid(
            self, app, create_user, create_cert):
        from models.certificate import Certificate
        from models.policy import ApprovalRequest

        user = create_user(username='backup_idempotence_remap')
        issued = create_cert(cn='remapped-approval.example.test')
        with app.app_context():
            certificate = Certificate.query.filter_by(refid=issued['refid']).first()
            ApprovalRequest.query.filter_by(requester_id=user['id']).delete()
            request = ApprovalRequest(
                request_type='certificate',
                certificate_id=certificate.id,
                requester_id=user['id'],
                status='approved',
                created_at=CREATED_AT,
            )
            db.session.add(request)
            db.session.commit()

            payload = {'approval_requests': _archived(
                'approval_requests', lambda row: row['requester_id'] == user['id'])}
            ApprovalRequest.query.filter_by(requester_id=user['id']).delete()
            db.session.commit()

            # The same certificate, numbered differently on the installation
            # the archive came from.
            row = payload['approval_requests'][0]
            row['certificate_id'] = certificate.id + 100000
            assert row['certificate_id_ref'] == {'refid': issued['refid']}

            try:
                _restore(payload)
                restored = _approvals_of(user)
                assert len(restored) == 1, 'the request was not restored'
                assert restored[0].certificate_id == certificate.id, \
                    'the request kept the number it had on the source'
            finally:
                ApprovalRequest.query.filter_by(requester_id=user['id']).delete()
                db.session.commit()

    def test_a_certificate_this_installation_does_not_have_stops_the_restore(
            self, app, create_user, create_cert):
        from models.certificate import Certificate
        from models.policy import ApprovalRequest

        user = create_user(username='backup_idempotence_unknown_cert')
        issued = create_cert(cn='unknown-approval.example.test')
        with app.app_context():
            certificate = Certificate.query.filter_by(refid=issued['refid']).first()
            ApprovalRequest.query.filter_by(requester_id=user['id']).delete()
            request = ApprovalRequest(
                request_type='certificate',
                certificate_id=certificate.id,
                requester_id=user['id'],
                status='approved',
                created_at=CREATED_AT,
            )
            db.session.add(request)
            db.session.commit()

            payload = {'approval_requests': _archived(
                'approval_requests', lambda row: row['requester_id'] == user['id'])}
            ApprovalRequest.query.filter_by(requester_id=user['id']).delete()
            db.session.commit()

            payload['approval_requests'][0]['certificate_id_ref'] = {
                'refid': 'a-certificate-that-is-not-here'}
            try:
                with pytest.raises(RestoreValidationError, match='certificates'):
                    _restore(payload)
                assert _approvals_of(user) == [], \
                    'the request was attached to whatever held that number here'
            finally:
                ApprovalRequest.query.filter_by(requester_id=user['id']).delete()
                db.session.commit()


class TestAcmeClientOrdersAreRestoredOnce:
    ORDER_URL = 'https://acme.example.test/order/idempotence-1'

    def test_a_second_restore_does_not_add_a_second_order(self, app):
        from models.acme_models import AcmeClientOrder

        with app.app_context():
            AcmeClientOrder.query.filter_by(order_url=self.ORDER_URL).delete()
            order = AcmeClientOrder(
                domains=json.dumps(['idempotent-order.example.test']),
                challenge_type='dns-01',
                environment='staging',
                status='valid',
                order_url=self.ORDER_URL,
                finalize_url='https://acme.example.test/finalize/1',
            )
            db.session.add(order)
            db.session.commit()

            payload = {'acme_client_orders': _archived(
                'acme_client_orders',
                lambda row: row['order_url'] == self.ORDER_URL)}
            assert len(payload['acme_client_orders']) == 1

            AcmeClientOrder.query.filter_by(order_url=self.ORDER_URL).delete()
            db.session.commit()

            try:
                _restore(payload)
                first = AcmeClientOrder.query.filter_by(order_url=self.ORDER_URL).all()
                assert len(first) == 1, 'the order was not restored'
                restored_id = first[0].id
                assert first[0].status == 'valid'

                _restore(payload)
                again = AcmeClientOrder.query.filter_by(order_url=self.ORDER_URL).all()
                assert len(again) == 1, \
                    'restoring the same archive twice left two orders for one URL'
                assert again[0].id == restored_id
            finally:
                AcmeClientOrder.query.filter_by(order_url=self.ORDER_URL).delete()
                db.session.commit()

    def test_an_order_already_here_is_brought_back_to_what_the_archive_holds(self, app):
        from models.acme_models import AcmeClientOrder

        with app.app_context():
            AcmeClientOrder.query.filter_by(order_url=self.ORDER_URL).delete()
            order = AcmeClientOrder(
                domains=json.dumps(['idempotent-order.example.test']),
                challenge_type='dns-01',
                environment='staging',
                status='valid',
                order_url=self.ORDER_URL,
            )
            db.session.add(order)
            db.session.commit()

            payload = {'acme_client_orders': _archived(
                'acme_client_orders',
                lambda row: row['order_url'] == self.ORDER_URL)}

            order.status = 'invalid'
            order.error_message = 'changed after the backup'
            db.session.commit()

            try:
                _restore(payload)
                back = AcmeClientOrder.query.filter_by(order_url=self.ORDER_URL).all()
                assert len(back) == 1
                assert back[0].status == 'valid', \
                    'the existing order kept the state the archive replaces'
                assert back[0].error_message is None
            finally:
                AcmeClientOrder.query.filter_by(order_url=self.ORDER_URL).delete()
                db.session.commit()


class TestRowsThisRestoreHasJustCreated:
    """The plan indexes the installation as it was before the first write, so
    a full archive would not find the users and certificates it is itself
    putting back; the identity is looked up again on the session."""

    def test_the_requester_restored_by_the_same_pass_is_found(self, app, pending_approval):
        from models import User
        from models.policy import ApprovalRequest

        user, payload = pending_approval
        latecomer = 'backup_idempotence_late_requester'
        payload['approval_requests'][0]['requester_id_ref'] = {'username': latecomer}
        with app.app_context():
            User.query.filter_by(username=latecomer).delete()
            db.session.commit()

            # Built while that user is still absent, exactly as a restore
            # builds it before applying its own users section.
            plan = RestorePlan.build(payload)
            try:
                with single_transaction():
                    db.session.add(User(
                        username=latecomer, role='operator', active=True,
                        email=f'{latecomer}@example.test',
                        password_hash='not-a-usable-hash'))
                    _service()._restore_approval_requests(payload, {}, plan)

                restored_for = User.query.filter_by(username=latecomer).first()
                requests = ApprovalRequest.query.filter_by(
                    requester_id=restored_for.id).all()
                assert len(requests) == 1, \
                    'the request was not attached to the user restored with it'
                assert requests[0].created_at == CREATED_AT
            finally:
                ApprovalRequest.query.filter_by(
                    requester_id=db.session.query(User.id).filter_by(
                        username=latecomer).scalar_subquery()).delete(
                            synchronize_session=False)
                User.query.filter_by(username=latecomer).delete()
                db.session.commit()
