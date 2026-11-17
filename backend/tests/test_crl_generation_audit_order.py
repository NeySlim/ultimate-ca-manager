"""A generated CRL is recorded, or it is not generated.

`AuditService.log_ca` commits the session it is given and rolls all of it back
when it cannot write its own entry. Called between adding the CRL's metadata
row and committing it, it was the call that decided: an audit failure undid
the row, the commit that followed committed nothing, and the caller was handed
a CRL object describing a generation that left no trace.

The same shape as the deployment targets and the CRL schedule before it.
"""
import pytest

from models import db


@pytest.fixture
def audit_always_fails(monkeypatch):
    from models.audit_log import AuditLog

    def failing_hash(self, *args, **kwargs):
        raise RuntimeError('audit hash chain unavailable')

    monkeypatch.setattr(AuditLog, 'compute_hash', failing_hash, raising=False)


class TestTheAnswerAndTheLedgerAgree:
    def test_a_failed_audit_is_not_answered_as_a_generation(
            self, app, auth_client, create_ca, audit_always_fails):
        from models import CRLMetadata

        ca = create_ca(cn='CRL Generation Audit Order CA')

        with app.app_context():
            before = CRLMetadata.query.filter_by(ca_id=ca['id'],
                                                 is_delta=False).count()

        response = auth_client.post(f"/api/v2/crl/{ca['id']}/regenerate")

        with app.app_context():
            after = CRLMetadata.query.filter_by(ca_id=ca['id'],
                                                is_delta=False).count()

        announced = response.status_code == 200
        recorded = after > before
        assert announced == recorded, (
            f'the route answered {response.status_code} and the ledger holds '
            f'{after - before} new row(s): the audit entry decided whether the '
            'generation was kept and nothing told the caller')

    def test_the_ordinary_path_records_the_generation(
            self, app, auth_client, create_ca):
        from models import CRLMetadata

        ca = create_ca(cn='CRL Generation Audit Order OK CA')
        response = auth_client.post(f"/api/v2/crl/{ca['id']}/regenerate")

        assert response.status_code == 200, response.data
        with app.app_context():
            assert CRLMetadata.query.filter_by(ca_id=ca['id'],
                                               is_delta=False).count() >= 1
