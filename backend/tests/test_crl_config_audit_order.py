"""When the CRL schedule is recorded, relative to being saved.

`AuditService.log_action` commits the session it is given, and rolls the whole
of it back when it cannot write its own entry. Called before the business
commit it is therefore the call that decides whether the change survives: an
audit failure undid the schedule, the `safe_commit` that followed committed an
empty session and answered that all was well, and the route replied with the
values it had just lost.

The deployment routes carry the same rule, written out at
`api/v2/deploy.py`, and the backup routines learned it the same way.
"""
import pytest

from models import db


@pytest.fixture
def audit_always_fails(monkeypatch):
    from models.audit_log import AuditLog

    def failing_hash(self, *args, **kwargs):
        raise RuntimeError('audit hash chain unavailable')

    monkeypatch.setattr(AuditLog, 'compute_hash', failing_hash, raising=False)


CASES = (
    ('/api/v2/crl/{ca_id}/config', {'validity_days': 21},
     'crl_validity_days', 21),
    ('/api/v2/crl/{ca_id}/delta-config', {'enabled': True, 'interval': 12},
     'delta_crl_interval', 12),
)


class TestTheScheduleAndTheAnswerAgree:
    @pytest.mark.parametrize('route, payload, column, expected', CASES)
    def test_a_failed_audit_is_not_answered_as_a_change(
            self, app, auth_client, create_ca, audit_always_fails,
            route, payload, column, expected):
        from models import CA

        ca = create_ca(cn=f'CRL Audit Order {column}')
        response = auth_client.post(route.format(ca_id=ca['id']), json=payload)

        with app.app_context():
            saved = getattr(db.session.get(CA, ca['id']), column)

        announced = response.status_code == 200
        assert announced == (saved == expected), (
            f'the route answered {response.status_code} and the column holds '
            f'{saved!r}: the audit entry decided the fate of the change and '
            'nothing told the caller')

    @pytest.mark.parametrize('route, payload, column, expected', CASES)
    def test_the_ordinary_path_still_saves_and_records(
            self, app, auth_client, create_ca, route, payload, column,
            expected):
        from models import CA

        ca = create_ca(cn=f'CRL Audit Order OK {column}')
        response = auth_client.post(route.format(ca_id=ca['id']), json=payload)

        assert response.status_code == 200, response.data
        with app.app_context():
            assert getattr(db.session.get(CA, ca['id']), column) == expected
