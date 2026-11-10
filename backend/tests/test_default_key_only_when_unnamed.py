"""A request (or its template) that names its key never computes the default key: a policy
that refuses every default candidate still issues the key it allows."""
import json
import uuid

import pytest

from models import ApprovalRequest, CertificatePolicy, CertificateTemplate, SystemConfig, db
from tests.test_approval_template_issuance import _mk_approval_id, _requester_id
from tests.fixtures.templates import templates_created_here_removed


@pytest.fixture(autouse=True, scope='module')
def _templates_stay_in_this_module(app):
    with templates_created_here_removed(app):
        yield


@pytest.fixture
def tsa_settings(app):
    keys = ('tsa_signer_cert_refid', 'tsa_ca_refid')
    with app.app_context():
        saved = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None) for k in keys}
    yield
    with app.app_context():
        SystemConfig.query.filter(SystemConfig.key.in_(keys)).delete(synchronize_session=False)
        db.session.add_all(SystemConfig(key=k, value=v) for k, v in saved.items() if v is not None)
        db.session.commit()


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


@pytest.fixture
def only(app):
    made = []

    def make(allowed, ca_id=None, template_id=None):
        with app.app_context():
            pol = CertificatePolicy(name=f'only-{uuid.uuid4().hex[:8]}', policy_type='issuance',
                                    ca_id=ca_id, template_id=template_id, requires_approval=False,
                                    min_approvers=1, is_active=True, priority=100)
            pol.set_rules({'allowed_key_types': allowed})
            db.session.add(pol)
            db.session.commit()
            made.append(pol.id)
    yield make
    with app.app_context():
        CertificatePolicy.query.filter(CertificatePolicy.id.in_(made)).delete(synchronize_session=False)
        db.session.commit()


@pytest.mark.parametrize('allowed, body', [
    ('RSA-4096', {'key_type': 'rsa', 'key_size': '4096'}),
    ('EC-P521', {'key_type': 'ec', 'curve': 'P-521'}),
    ('EC-P521', {'key_type': 'ec', 'key_size': 'P-521'}),
])
def test_direct_issuance_of_the_only_allowed_key(auth_client, create_ca, only, allowed, body):
    ca = create_ca(cn=f'Named key CA {uuid.uuid4().hex[:6]}')
    only([allowed], ca_id=ca['id'])
    r = _post(auth_client, '/api/v2/certificates',
              {'cn': 'named-key.example.test', 'ca_id': ca['id'], 'validity_days': 30, **body})
    assert r.status_code == 201, r.get_json()


def test_template_key_under_a_template_policy(app, auth_client, create_ca, only):
    ca = create_ca(cn=f'Named key tpl CA {uuid.uuid4().hex[:6]}')
    with app.app_context():
        tpl = CertificateTemplate(name=f'rsa4096-{uuid.uuid4().hex[:6]}', template_type='web_server',
                                  key_type='RSA-4096', validity_days=30, digest='sha256',
                                  extensions_template='{}')
        db.session.add(tpl)
        db.session.commit()
        tpl_id = tpl.id
    only(['RSA-4096'], template_id=tpl_id)
    r = _post(auth_client, '/api/v2/certificates',
              {'cn': 'named-key-tpl.example.test', 'ca_id': ca['id'], 'template_id': tpl_id,
               'validity_days': 30})
    assert r.status_code == 201, r.get_json()


def test_approved_request_of_the_only_allowed_key(app, create_ca, only):
    from api.v2.policies import _issue_approved_certificate
    ca = create_ca(cn=f'Named key approval CA {uuid.uuid4().hex[:6]}')
    only(['RSA-4096'], ca_id=ca['id'])
    approval_id = _mk_approval_id(app, _requester_id(app), {
        'cn': 'named-key-approval.example.test', 'ca_id': ca['id'],
        'key_type': 'rsa', 'key_size': '4096', 'validity_days': 30})
    with app.app_context():
        assert _issue_approved_certificate(db.session.get(ApprovalRequest, approval_id))['id']
        db.session.commit()


def test_tsa_signer_of_the_only_allowed_key(auth_client, create_ca, only, tsa_settings):
    ca = create_ca(cn=f'Named key TSA CA {uuid.uuid4().hex[:6]}')
    only(['RSA-4096'], ca_id=ca['id'])
    r = _post(auth_client, '/api/v2/tsa/signer-certificate',
              {'ca_id': ca['id'], 'select': False, 'key_type': 'rsa', 'key_size': '4096'})
    assert r.status_code == 200, r.get_json()
