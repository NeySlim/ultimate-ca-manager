"""The REST form and its approved deferred issuance each count one certificate
in the CA's issuance counter (``certificate_authorities.serial``)."""
import json

import pytest

from api.v2.policies import _issue_approved_certificate
from models import CA, Certificate, db
from models.policy import ApprovalRequest, CertificatePolicy
from tests.seeded_rows import delete_cas
from tests.test_approval_template_issuance import _mk_approval_id, _requester_id


@pytest.fixture(autouse=True)
def _remove_what_the_test_created(app):
    def ids(model):
        with app.app_context():
            return {r.id for r in model.query.with_entities(model.id)}
    before = {m: ids(m) for m in (CA, ApprovalRequest, CertificatePolicy)}
    yield
    with app.app_context():
        for m in (ApprovalRequest, CertificatePolicy):
            new = {r.id for r in m.query.with_entities(m.id)} - before[m]
            if new:
                m.query.filter(m.id.in_(new)).delete(synchronize_session=False)
        delete_cas(CA.query.filter(CA.id.notin_(before[CA])))
        db.session.commit()


def _count(app, ca_id):
    with app.app_context():
        return (db.session.get(CA, ca_id).serial or 0,
                Certificate.query.filter_by(caref=db.session.get(CA, ca_id).refid).count())


def test_rest_issuance_counts_each_certificate(app, auth_client, create_ca):
    ca = create_ca(cn='REST issuance count CA')
    for i in range(2):
        r = auth_client.post('/api/v2/certificates', data=json.dumps(
            {'cn': f'count-{i}.example.test', 'ca_id': ca['id'], 'validity_days': 30}),
            content_type='application/json')
        assert r.status_code in (200, 201), r.data
    with app.app_context():
        assert db.session.get(CA, ca['id']).serial == 2
    assert json.loads(auth_client.get(f"/api/v2/cas/{ca['id']}").data)['data']['serial'] == 2


def test_approved_issuance_counts_the_certificate(app, create_ca):
    ca = create_ca(cn='Approval issuance count CA')
    assert _count(app, ca['id']) == (0, 0)
    approval_id = _mk_approval_id(app, _requester_id(app), {
        'cn': 'approved-count.example.test', 'ca_id': ca['id'], 'cert_type': 'server'})
    with app.app_context():
        _issue_approved_certificate(db.session.get(ApprovalRequest, approval_id))
    assert _count(app, ca['id']) == (1, 1)
