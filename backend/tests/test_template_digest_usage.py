"""Regression tests for discussion #207 confirmed bugs.

1. The certificate-menu issuance path must sign with the template digest
   (it was hardcoded to SHA-256) and persist template_id on the issued row.
2. Template listing/detail must expose a live usage_count computed from
   Certificate.template_id (the UI displayed a field the API never sent).
"""
import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from tests.conftest import get_json
from tests.fixtures.templates import templates_created_here_removed


@pytest.fixture(autouse=True, scope='module')
def _templates_stay_in_this_module(app):
    with templates_created_here_removed(app):
        yield


CONTENT_JSON = 'application/json'

TEMPLATE_SHA384 = {
    'name': 'digest-384-tpl',
    'template_type': 'custom',
    'key_type': 'RSA-2048',
    'validity_days': 90,
    'digest': 'sha384',
    'extensions_template': json.dumps({
        'key_usage': ['digitalSignature', 'keyEncipherment'],
        'extended_key_usage': ['serverAuth'],
    }),
}


def _issue_cert(auth_client, ca_id, cn, **extra):
    payload = {'cn': cn, 'ca_id': ca_id, 'key_type': 'rsa', 'key_size': 2048,
               'validity_days': 90}
    payload.update(extra)
    return auth_client.post('/api/v2/certificates',
                            data=json.dumps(payload), content_type=CONTENT_JSON)


def _create_template(auth_client, **overrides):
    data = {**TEMPLATE_SHA384}
    data.update(overrides)
    r = auth_client.post('/api/v2/templates',
                         data=json.dumps(data), content_type=CONTENT_JSON)
    assert r.status_code in (200, 201), r.data
    body = get_json(r)
    return body.get('data', body)


def _issued_cert_obj(app, cert_id):
    with app.app_context():
        from models import Certificate, db
        row = db.session.get(Certificate, cert_id)
        assert row is not None
        pem = base64.b64decode(row.crt)
    return x509.load_pem_x509_certificate(pem, default_backend())


class TestTemplateDigestHonored:

    def test_sha384_template_signs_sha384(self, app, auth_client, create_ca):
        ca = create_ca(cn='Digest Tpl CA')
        tpl = _create_template(auth_client, name='digest-384-a')

        r = _issue_cert(auth_client, ca['id'], 'digest-a.test', template_id=tpl['id'])
        assert r.status_code in (200, 201), r.data
        cert_id = get_json(r)['data']['id']

        cert = _issued_cert_obj(app, cert_id)
        assert cert.signature_hash_algorithm.name == 'sha384'

    def test_no_template_keeps_sha256(self, app, auth_client, create_ca):
        ca = create_ca(cn='Digest Default CA')
        r = _issue_cert(auth_client, ca['id'], 'digest-default.test')
        assert r.status_code in (200, 201), r.data
        cert_id = get_json(r)['data']['id']

        cert = _issued_cert_obj(app, cert_id)
        assert cert.signature_hash_algorithm.name == 'sha256'

    def test_unknown_template_id_rejected(self, auth_client, create_ca):
        ca = create_ca(cn='Digest Unknown Tpl CA')
        r = _issue_cert(auth_client, ca['id'], 'digest-bad.test', template_id=999999)
        assert r.status_code == 404


class TestTemplateUsageCount:

    def test_usage_count_persisted_and_counted(self, app, auth_client, create_ca):
        ca = create_ca(cn='Usage Count CA')
        tpl = _create_template(auth_client, name='usage-count-tpl')

        for i in range(2):
            r = _issue_cert(auth_client, ca['id'], f'usage-{i}.test',
                            template_id=tpl['id'])
            assert r.status_code in (200, 201), r.data
            cert_id = get_json(r)['data']['id']
            with app.app_context():
                from models import Certificate, db
                row = db.session.get(Certificate, cert_id)
                assert row.template_id == tpl['id']

        r = auth_client.get('/api/v2/templates')
        assert r.status_code == 200
        listed = {t['id']: t for t in get_json(r)['data']}
        assert listed[tpl['id']]['usage_count'] == 2

        r = auth_client.get(f"/api/v2/templates/{tpl['id']}")
        assert get_json(r)['data']['usage_count'] == 2

    def test_unused_template_counts_zero(self, auth_client):
        tpl = _create_template(auth_client, name='usage-zero-tpl')
        r = auth_client.get(f"/api/v2/templates/{tpl['id']}")
        assert get_json(r)['data']['usage_count'] == 0
