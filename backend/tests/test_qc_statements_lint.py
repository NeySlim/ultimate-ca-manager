"""The etsi lint profile and the qcStatements a qualified template issues."""
import base64
import json
import itertools

import pytest

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import CA, Certificate, CertificateTemplate, db
from services import cert_linting_service as L
from tests.test_acme_profile_template import _drop_template
from tests.test_csr_sign_extra_names import _upload

needs_pkilint = pytest.mark.skipif(not L.linters_status()['pkilint'], reason='pkilint not installed')
_SEQ = itertools.count(1)

QC = {
    'compliance': True, 'type': 'esign', 'sscd': True,
    'pds': [{'url': 'https://pki.example.test/pds_en.pdf', 'language': 'en'}],
    'retention_period': 10,
    'limit_value': {'currency': 'EUR', 'amount': 1000, 'exponent': 0},
    'semantics': 'eidas-natural',
}


def _person_csr():
    name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, 'FR'),
        x509.NameAttribute(NameOID.GIVEN_NAME, 'Jean'),
        x509.NameAttribute(NameOID.SURNAME, 'Dupont'),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, 'FR/FR/0123456'),
        x509.NameAttribute(NameOID.COMMON_NAME, 'Jean Dupont')])
    return (x509.CertificateSigningRequestBuilder().subject_name(name)
            .add_extension(x509.SubjectAlternativeName([x509.RFC822Name('jean@example.com')]),
                           critical=False)
            .add_extension(x509.KeyUsage(
                digital_signature=False, content_commitment=True, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .sign(ec.generate_private_key(ec.SECP256R1()), hashes.SHA256()))


def _sign_person(app, auth_client, ca_id, tpl_id):
    csr_id = _upload(auth_client, _person_csr())
    r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={
        'ca_id': ca_id, 'validity_days': 30, 'template_id': tpl_id, 'cert_type': 'email'})
    assert r.status_code in (200, 201), r.get_json()
    with app.app_context():
        return csr_id, db.session.get(Certificate, csr_id).crt


@pytest.fixture
def qualified_cert(app, auth_client, create_ca):
    ca = create_ca(cn='QC lint CA')
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        row.aia_ca_issuers_enabled = True
        row.aia_ca_issuers_url = json.dumps(['http://pki.example.com/ca.crt'])
        # Public names only: the ETSI profile flags an internal domain (#421).
        row.cdp_enabled = True
        row.set_cdp_urls(['http://pki.example.com/crl.pem'])
        db.session.commit()
        tpl = CertificateTemplate(
            name=f'qc-lint-{next(_SEQ)}', template_type='custom', key_type='RSA-2048',
            validity_days=30, digest='sha256', dn_template=json.dumps({'CN': '{cn}'}),
            extensions_template=json.dumps({
                'key_usage': ['contentCommitment'], 'extended_key_usage': ['emailProtection'],
                'qc_statements': QC, 'certificate_policies': ['0.4.0.194112.1.2']}))
        db.session.add(tpl)
        db.session.commit()
        tpl_id = tpl.id
    cert_id, crt = _sign_person(app, auth_client, ca['id'], tpl_id)
    yield {'id': cert_id, 'crt': crt}
    _drop_template(app, tpl_id)


def test_etsi_is_a_listed_profile(auth_client):
    r = auth_client.get('/api/v2/certificates/lint/status')
    assert 'etsi' in r.get_json()['data']['profiles']


@needs_pkilint
def test_etsi_detects_a_qualified_type_and_finds_no_error(qualified_cert):
    r = L.lint_certificate_pem(qualified_cert['crt'], 'etsi')
    assert r['available'] is True
    assert r['detected_type'] and r['detected_type'].upper().startswith('QCP')
    errors = [f['code'] for f in r['findings'] if f['severity'] in ('error', 'fatal')]
    assert errors == [], errors


@needs_pkilint
def test_etsi_flags_a_missing_qc_type(app, auth_client, create_ca):
    """The oracle is not blind: a QCP-n-qscd certificate without QcType is reported."""
    ca = create_ca(cn='QC lint negative CA')
    with app.app_context():
        tpl = CertificateTemplate(
            name=f'qc-lint-neg-{next(_SEQ)}', template_type='custom', key_type='RSA-2048',
            validity_days=30, digest='sha256', dn_template=json.dumps({'CN': '{cn}'}),
            extensions_template=json.dumps({
                'qc_statements': {'compliance': True, 'sscd': True}, 'certificate_policies': ['0.4.0.194112.1.2']}))
        db.session.add(tpl)
        db.session.commit()
        tpl_id = tpl.id
    try:
        _, crt = _sign_person(app, auth_client, ca['id'], tpl_id)
        result = L.lint_certificate_pem(crt, 'etsi')
        assert any('qc_type_qualified_statement_absent' in f['code'] for f in result['findings']), \
            result['findings']
    finally:
        _drop_template(app, tpl_id)


@needs_pkilint
def test_etsi_endpoint(auth_client, qualified_cert):
    r = auth_client.get(f"/api/v2/certificates/{qualified_cert['id']}/lint?profile=etsi")
    assert r.status_code == 200
    assert r.get_json()['data']['profile'] == 'etsi'
