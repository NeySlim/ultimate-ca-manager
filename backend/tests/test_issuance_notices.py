"""A request honoured on other terms than the ones asked for says so.

Neither a refusal nor what was requested: the certificate is issued, the
answer is a 201, and the only trace of the difference is an expiry date
nobody looks at until it matters. The paths that shorten a validity now name
what shortened it in ``meta.notices``.
"""
import json

import pytest

from models import db
from models.policy import CertificatePolicy
from tests.conftest import get_json


@pytest.fixture()
def capping_policy(app):
    """An active, unscoped policy that caps validity at 30 days."""
    with app.app_context():
        policy = CertificatePolicy(name='Notice Cap', policy_type='issuance',
                                   is_active=True, priority=100,
                                   requires_approval=False, min_approvers=1)
        policy.set_rules({'max_validity_days': 30})
        db.session.add(policy)
        db.session.commit()
        pid = policy.id
    yield pid
    with app.app_context():
        row = db.session.get(CertificatePolicy, pid)
        if row:
            db.session.delete(row)
            db.session.commit()


@pytest.fixture()
def issue(auth_client, create_ca):
    """POST /certificates and hand back the whole body, meta included."""
    ca = create_ca(cn='Notice Test CA')
    counter = [0]

    def _issue(validity_days):
        counter[0] += 1
        return auth_client.post('/api/v2/certificates', data=json.dumps({
            'cn': f'notice-{counter[0]}.example.com',
            'ca_id': ca.get('id', ca.get('ca_id')),
            'validity_days': validity_days,
        }), content_type='application/json')
    return _issue


def _notices(answer):
    return (get_json(answer).get('meta') or {}).get('notices') or []


class TestPolicyCapIsAnnounced:
    def test_the_notice_names_the_policy_and_both_durations(
            self, issue, capping_policy):
        answer = issue(365)
        assert answer.status_code == 201, answer.data[:300]
        notices = _notices(answer)
        assert len(notices) == 1, get_json(answer).get('meta')
        assert '30' in notices[0] and '365' in notices[0]
        assert 'Notice Cap' in notices[0]

    def test_the_certificate_really_is_the_shorter_one(
            self, issue, capping_policy):
        answer = issue(365)
        assert get_json(answer)['data']['days_remaining'] == 30

    def test_nothing_is_said_when_the_request_is_honoured(
            self, issue, capping_policy):
        answer = issue(10)
        assert answer.status_code == 201
        assert _notices(answer) == []


class TestWithoutAPolicy:
    def test_a_plain_issuance_carries_no_notice(self, issue):
        answer = issue(200)
        assert answer.status_code == 201
        assert _notices(answer) == []
