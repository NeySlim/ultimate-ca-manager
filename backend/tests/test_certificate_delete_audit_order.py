"""Deleting a certificate leaves the database and the disk agreeing.

The order was: detach the foreign keys other tables hold on this certificate,
delete its files, write the audit entry, then delete the row and commit.

Writing the audit entry commits the session it is given and rolls all of it
back when it cannot write its own. Called there, it undid the detachment that
had not been committed yet, **after** the files were already gone. The delete
that followed then hit the foreign keys it had just un-detached, so the row
survived with no certificate, no request and no key on disk.

The files are still removed before the commit, which is its own question; what
this pins is that an audit entry never decides the outcome.
"""
import pytest

from models import db


@pytest.fixture
def audit_always_fails(monkeypatch):
    from models.audit_log import AuditLog

    def failing_hash(self, *args, **kwargs):
        raise RuntimeError('audit hash chain unavailable')

    monkeypatch.setattr(AuditLog, 'compute_hash', failing_hash, raising=False)


class TestTheDetachmentSurvivesTheAudit:
    """Pinned on the detachment rather than on the final outcome.

    SQLite enforces no foreign key, so the delete goes through there whether
    or not the detachment was rolled back, and the damage only shows on
    PostgreSQL. What both backends share is the invariant: once the files are
    gone, the rows that pointed at the certificate must stay detached.
    """

    def test_a_failed_audit_does_not_put_the_references_back(
            self, app, auth_client, create_ca, create_cert,
            audit_always_fails):
        import secrets

        from models import Certificate
        from models.acme_models import AcmeAccount, AcmeOrder
        from services.cert_service import CertificateService

        ca = create_ca(cn='Delete Audit Order CA')
        cert = create_cert(cn='delete-audit-order.example.test',
                           ca_id=ca['id'])

        with app.app_context():
            account_id = f'delaudit-{secrets.token_hex(4)}'
            db.session.add(AcmeAccount(account_id=account_id, jwk='{}',
                                       jwk_thumbprint=secrets.token_hex(8),
                                       status='valid'))
            db.session.flush()
            order = AcmeOrder(order_id=secrets.token_urlsafe(16),
                              account_id=account_id,
                              identifiers='[{"type":"dns","value":"d.test"}]',
                              status='valid', certificate_id=cert['id'])
            db.session.add(order)
            db.session.commit()
            order_id = order.order_id

        try:
            with app.app_context():
                CertificateService.delete_certificate(cert['id'],
                                                      username='tester')
                db.session.expire_all()
                still_pointing = AcmeOrder.query.filter_by(
                    order_id=order_id).one().certificate_id

            assert still_pointing is None, (
                'an order still points at the certificate: the audit entry '
                'rolled the detachment back after the files were deleted, and '
                'a database that enforces its foreign keys then refuses the '
                'delete outright')
        finally:
            with app.app_context():
                AcmeOrder.query.filter_by(order_id=order_id).delete(
                    synchronize_session=False)
                AcmeAccount.query.filter_by(account_id=account_id).delete(
                    synchronize_session=False)
                row = db.session.get(Certificate, cert['id'])
                if row is not None:
                    db.session.delete(row)
                db.session.commit()


class TestTheLedgerNamesTheOperator:
    """Whoever pressed the button is who the entry names.

    `delete_certificate` takes a `username`, but it is not the name that goes
    in the ledger and never was: `log_certificate` passed none, so the entry
    was attributed to `g.current_user`. Two internal callers hand the function
    a fixed name instead of a person's -- `username='system'` from the
    expired-revoked purge in `services/crl/query.py`, `username='acme_proxy'`
    from the proxy -- and the purge runs inside an operator's request, reached
    from `generate_crl`. Forwarding that argument to the audit call therefore
    replaces the operator with `system` on every certificate the purge removes,
    in the one record that is supposed to say who did it.
    """

    def test_an_internal_caller_does_not_take_the_operators_place(
            self, app, auth_client, create_ca, create_cert):
        from models import AuditLog
        from services.cert_service import CertificateService

        ca = create_ca(cn='PurgeAttribution CA')
        cert = create_cert(ca_id=ca['id'], cn='purge-attribution.example')

        # The name the purge passes, from inside a request an operator made.
        with auth_client.application.test_request_context():
            from flask import g
            from models import User
            g.current_user = User.query.filter_by(username='admin').first()
            g.user_id = g.current_user.id
            assert CertificateService.delete_certificate(
                cert_id=cert['id'], username='system') is True

        with app.app_context():
            entry = AuditLog.query.filter_by(
                action='cert_deleted',
                resource_name='purge-attribution.example').first()
        assert entry is not None, 'the deletion was not recorded at all'
        assert entry.username == 'admin', (
            'the ledger credits the internal caller instead of the operator '
            f'whose request it is: {entry.username}')


class TestAFailedDeleteIsNotSilent:
    """A deletion that fails halfway leaves the disk and the database apart.

    The files are unlinked before the row is deleted, and a rollback cannot
    put them back. Moving the audit entry after the commit was right, but it
    left the failing path writing nothing at all: the certificate is listed,
    its key and PEM are gone, and no record says why. The entry that used to
    be there claimed success, which was worse; the answer is one that says
    what happened.
    """

    def test_the_failure_is_recorded_with_its_reason(
            self, app, auth_client, create_ca, create_cert, monkeypatch):
        from models import db, AuditLog
        from services.cert_service import CertificateService

        ca = create_ca(cn='HalfDeleted CA')
        cert = create_cert(ca_id=ca['id'], cn='half-deleted.example')

        def _refuse(_obj):
            raise RuntimeError('delete refused')

        with auth_client.application.test_request_context():
            from flask import g
            from models import User
            g.current_user = User.query.filter_by(username='admin').first()
            g.user_id = g.current_user.id
            monkeypatch.setattr(db.session, 'delete', _refuse, raising=False)
            assert CertificateService.delete_certificate(
                cert_id=cert['id'],
                username='admin') is False
            monkeypatch.undo()

        with app.app_context():
            entry = AuditLog.query.filter_by(
                action='cert_deleted',
                resource_name='half-deleted.example').first()
        assert entry is not None, (
            'the files are gone and nothing in the ledger says the deletion '
            'failed')
        assert entry.success is False, (
            'the ledger reports a success for a deletion that did not happen')


def test_the_scts_kept_under_its_number_go_with_it(app, create_ca, create_cert):
    """SQLite gives the number to the next certificate, which would inherit them."""
    from models import SystemConfig
    from services.cert_service import CertificateService
    ca = create_ca(cn='SCT setting CA')
    cert = create_cert(cn='sct-setting.example.test', ca_id=ca['id'])
    key = f"cert_scts_{cert['id']}"
    with app.app_context():
        db.session.add(SystemConfig(key=key, value='[]'))
        db.session.commit()
        assert CertificateService.delete_certificate(cert['id'])
        assert SystemConfig.query.filter_by(key=key).first() is None
