"""A policy's DNS pattern scopes it by DNS label, case-insensitively (RFC 4343)."""
import json
import uuid

import pytest

from services.policy_service import PolicyEvaluationService
from tests.test_approval_fail_closed import _approval_policy, _cleanup, _operator_client


class _Policy:
    def __init__(self, pattern):
        self._rules = {'san_restrictions': {'dns_pattern': pattern}}

    def get_rules(self):
        return self._rules


@pytest.mark.parametrize('pattern,name,in_scope', [
    ('*.company.com', 'www.company.com', True),
    ('*.company.com', 'a.b.company.com', True),
    ('*.company.com', 'company.com', False),
    ('*.company.com', 'evilcompany.com', False),
    ('company.com', 'www.company.com', True),
    ('company.com', 'company.com', True),
    ('company.com', 'evilcompany.com', False),
    ('company.com', 'company.com.evil.org', False),
    ('.company.com', 'www.company.com', True),
    ('.company.com', 'evilcompany.com', False),
    # case and the root label are not part of the name (RFC 4343, RFC 1034 §3.1)
    ('*.company.com', 'WWW.Company.COM.', True),
    ('*.Company.com.', 'www.company.com', True),
    ('company.com', 'DNS:www.company.com', True),
    ('*.company.com', '*.company.com', True),
    ('*.', '*.company.com', True),
    ('*.', 'www.company.com', False),
])
def test_policy_dns_pattern_matches_by_label(pattern, name, in_scope):
    assert PolicyEvaluationService._matches_rules(_Policy(pattern), cn=name) is in_scope


def test_pattern_is_matched_against_the_sans_too():
    policy = _Policy('*.company.com')
    assert PolicyEvaluationService._matches_rules(policy, cn='other.test', san_list=['api.company.com'])
    assert not PolicyEvaluationService._matches_rules(policy, cn='other.test', san_list=['company.com.evil.org'])


def test_policy_dns_pattern_wildcard_scopes_subdomains(app, create_ca, create_user):
    ca = create_ca(cn='DNS pattern approval CA')
    pid = _approval_policy(app, ca['id'], {'san_restrictions': {'dns_pattern': '*.company.com'}},
                           name='dns-label')
    operator = _operator_client(app, create_user)
    try:
        r = operator.post('/api/v2/certificates', content_type='application/json', data=json.dumps(
            {'cn': 'www.company.com', 'ca_id': ca['id'], 'san_dns': ['www.company.com'],
             'validity_days': 30}))
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['data'].get('approval_required') is True
        r = operator.post('/api/v2/certificates', content_type='application/json', data=json.dumps(
            {'cn': 'evilcompany.com', 'ca_id': ca['id'], 'san_dns': ['evilcompany.com'],
             'validity_days': 30}))
        assert r.status_code == 201, r.get_json()
    finally:
        _cleanup(app, pid, 'www.company.com')
        _cleanup(app, pid, 'evilcompany.com')


@pytest.mark.parametrize('pattern', ['*.company.com, company.com', '*.company.com company.com',
                                     'company.com,', ['*.company.com']])
def test_a_list_in_the_dns_pattern_is_refused_on_save(app, auth_client, pattern):
    from models import db
    from models.policy import CertificatePolicy
    name = f'dns-list-{uuid.uuid4().hex[:8]}'
    rules = {'san_restrictions': {'dns_pattern': pattern}}
    try:
        r = auth_client.post('/api/v2/policies', content_type='application/json',
                             data=json.dumps({'name': name, 'rules': rules}))
        assert r.status_code == 400, r.get_json()
        r = auth_client.post('/api/v2/policies', content_type='application/json', data=json.dumps(
            {'name': name, 'rules': {'san_restrictions': {'dns_pattern': '*.company.com'}}}))
        assert r.status_code in (200, 201), r.get_json()
        pid = r.get_json()['data']['id']
        r = auth_client.put(f'/api/v2/policies/{pid}', content_type='application/json',
                            data=json.dumps({'rules': rules}))
        assert r.status_code == 400, r.get_json()
        with app.app_context():
            stored = db.session.get(CertificatePolicy, pid).get_rules()
            assert stored['san_restrictions']['dns_pattern'] == '*.company.com'
    finally:
        with app.app_context():
            CertificatePolicy.query.filter_by(name=name).delete()
            db.session.commit()
