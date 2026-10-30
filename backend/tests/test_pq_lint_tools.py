"""Lint and decode tools on post-quantum certificates: findings, never an exception,
and the decoder names the key by its registry label."""
import base64
import json
import uuid

import pytest

from models import Certificate, db
from services import cert_linting_service
from tests.conftest import get_json
from tests.pqc_fixtures import fixture_bytes

PEMS = {'mldsa': fixture_bytes('mldsa65-cert.pem'), 'slhdsa': fixture_bytes('slhdsa-sha2-128s-cert.pem')}
LABELS = {'mldsa': 'ML-DSA-65', 'slhdsa': 'SLH-DSA-SHA2-128s'}

pytestmark = pytest.mark.skipif(not cert_linting_service.is_available(), reason='no linter installed')


@pytest.mark.parametrize('profile', cert_linting_service.VALID_PROFILES)
@pytest.mark.parametrize('kind', PEMS)
def test_lint_service_reports_findings(kind, profile):
    result = cert_linting_service.lint_certificate_pem(PEMS[kind].decode(), profile)
    assert result['available'] is True and 'pkilint' in result['linters']
    assert result['summary']['fatal'] == 0


@pytest.mark.parametrize('kind', PEMS)
def test_lint_route(kind, app, auth_client):
    refid = f'pq-lint-{uuid.uuid4().hex[:8]}'
    with app.app_context():
        row = Certificate(refid=refid, descr=refid, crt=base64.b64encode(PEMS[kind]).decode())
        db.session.add(row)
        db.session.commit()
        cert_id = row.id
    try:
        r = auth_client.get(f'/api/v2/certificates/{cert_id}/lint')
        assert r.status_code == 200, r.data[:300]
        assert get_json(r)['data']['available'] is True
    finally:
        with app.app_context():
            Certificate.query.filter_by(refid=refid).delete()
            db.session.commit()


@pytest.mark.parametrize('kind', PEMS)
def test_decode_cert_route_names_the_key(kind, auth_client):
    r = auth_client.post('/api/v2/tools/decode-cert', data=json.dumps({'pem': PEMS[kind].decode()}),
                         content_type='application/json')
    assert r.status_code == 200, r.data[:300]
    data = get_json(r)['data']
    assert data['public_key']['type'] == LABELS[kind] and data['public_key']['post_quantum'] is True
    assert data['signature_algorithm'] == LABELS[kind]


def test_decode_csr_route_names_the_key(auth_client):
    r = auth_client.post('/api/v2/tools/decode-csr',
                         data=json.dumps({'pem': fixture_bytes('mldsa65-csr.pem').decode()}),
                         content_type='application/json')
    assert r.status_code == 200, r.data[:300]
    data = get_json(r)['data']
    assert data['public_key']['type'] == 'ML-DSA-65' and data['is_signature_valid'] is True
