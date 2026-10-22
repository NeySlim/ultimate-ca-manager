"""qcStatements and policy OIDs of a template reach every issuance path that
reads template extensions, survive renewal, and show up decoded."""
import base64
import json
import itertools

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from models import CA, Certificate, CertificateTemplate, db
from tests.test_csr_sign_extra_names import _csr, _upload
from tests.test_acme_profile_template import _drop_template
from utils.qc_statements import QC_STATEMENTS_OID, decode_qc_statements

_SEQ = itertools.count(1)
QC = {
    'compliance': True, 'type': 'esign', 'sscd': True,
    'pds': [{'url': 'https://pki.example.test/pds_en.pdf', 'language': 'en'}],
    'retention_period': 10,
    'limit_value': {'currency': 'EUR', 'amount': 1000, 'exponent': 0},
    'semantics': 'eidas-natural',
}
POLICIES = ['0.4.0.194112.1.2']
CPS_URI = 'https://ca.example.test/cps'
CPS_OID = '1.3.6.1.4.1.99999.1'


def _tpl_ext(**extra):
    ext = {'key_usage': ['digitalSignature', 'contentCommitment'],
           'extended_key_usage': ['clientAuth'],
           'qc_statements': QC, 'certificate_policies': POLICIES}
    ext.update(extra)
    return ext


@pytest.fixture
def make_template(app):
    made = []

    def make(ext=None):
        with app.app_context():
            tpl = CertificateTemplate(
                name=f'qc-tpl-{next(_SEQ)}', template_type='custom', key_type='RSA-2048',
                validity_days=30, digest='sha256', dn_template=json.dumps({'CN': '{cn}'}),
                extensions_template=json.dumps(_tpl_ext() if ext is None else ext))
            db.session.add(tpl)
            db.session.commit()
            made.append(tpl.id)
            return tpl.id
    yield make
    for tpl_id in made:
        _drop_template(app, tpl_id)


@pytest.fixture
def cps_ca(app, create_ca):
    ca = create_ca(cn=f'QC CPS CA {next(_SEQ)}')
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        row.cps_enabled, row.cps_uri, row.cps_oid = True, CPS_URI, CPS_OID
        db.session.commit()
    return ca


def _cert(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


def _qc(cert):
    try:
        ext = cert.extensions.get_extension_for_oid(QC_STATEMENTS_OID)
    except x509.ExtensionNotFound:
        return None
    assert ext.critical is False
    return decode_qc_statements(ext.value.value)


def _policy_oids(cert):
    try:
        pol = cert.extensions.get_extension_for_class(x509.CertificatePolicies).value
    except x509.ExtensionNotFound:
        return None
    return [p.policy_identifier.dotted_string for p in pol]


def _assert_qualified(cert, with_cps=True):
    assert _qc(cert) == QC
    expected = ([CPS_OID] if with_cps else []) + POLICIES
    assert _policy_oids(cert) == expected


class TestIssueForm:
    def test_template_qualifies_the_certificate(self, app, auth_client, cps_ca, make_template):
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'qc-form.example.test', 'ca_id': cps_ca['id'], 'template_id': make_template()})
        assert r.status_code in (200, 201), r.get_json()
        cert = _cert(app, r.get_json()['data']['id'])
        _assert_qualified(cert)
        pol = cert.extensions.get_extension_for_class(x509.CertificatePolicies).value
        assert pol[0].policy_qualifiers == [CPS_URI]

    def test_no_cps_still_gets_template_policies(self, app, auth_client, create_ca, make_template):
        ca = create_ca(cn='QC no CPS CA')
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'qc-nocps.example.test', 'ca_id': ca['id'], 'template_id': make_template()})
        assert r.status_code in (200, 201), r.get_json()
        _assert_qualified(_cert(app, r.get_json()['data']['id']), with_cps=False)

    def test_template_without_qc_is_unchanged(self, app, auth_client, cps_ca, make_template):
        tpl = make_template({'extended_key_usage': ['clientAuth']})
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'qc-none.example.test', 'ca_id': cps_ca['id'], 'template_id': tpl})
        assert r.status_code in (200, 201), r.get_json()
        cert = _cert(app, r.get_json()['data']['id'])
        assert _qc(cert) is None
        assert _policy_oids(cert) == [CPS_OID]


class TestSignCsr:
    def test_sign_csr_form(self, app, auth_client, cps_ca, make_template):
        csr_id = _upload(auth_client, _csr('qc-sign.example.test'))
        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={
            'ca_id': cps_ca['id'], 'validity_days': 30, 'template_id': make_template()})
        assert r.status_code in (200, 201), r.get_json()
        _assert_qualified(_cert(app, csr_id))

    def test_bulk_sign(self, app, auth_client, cps_ca, make_template):
        csr_id = _upload(auth_client, _csr('qc-bulk.example.test'))
        r = auth_client.post('/api/v2/csrs/bulk/sign', json={
            'ids': [csr_id], 'ca_id': cps_ca['id'], 'validity_days': 30,
            'template_id': make_template()})
        assert r.status_code == 200, r.get_json()
        _assert_qualified(_cert(app, csr_id))

    def test_bound_template_acme_style(self, app, auth_client, cps_ca, make_template):
        from services.cert.service import CertificateService
        csr_id = _upload(auth_client, _csr('qc-acme.example.test'))
        with app.app_context():
            ca_refid = db.session.get(CA, cps_ca['id']).refid
            CertificateService.sign_csr(cert_id=csr_id, caref=ca_refid, validity_days=30,
                                        template_id=make_template())
        _assert_qualified(_cert(app, csr_id))

    def test_csr_cannot_bring_its_own_qc_statements(self, app, auth_client, cps_ca):
        csr = _csr('qc-csr.example.test')
        key = ec.generate_private_key(ec.SECP256R1())
        evil = (x509.CertificateSigningRequestBuilder()
                .subject_name(csr.subject)
                .add_extension(x509.UnrecognizedExtension(
                    QC_STATEMENTS_OID, bytes.fromhex('3008300606042b06010505')), critical=False)
                .sign(key, hashes.SHA256()))
        csr_id = _upload(auth_client, evil)
        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={
            'ca_id': cps_ca['id'], 'validity_days': 30})
        assert r.status_code in (200, 201), r.get_json()
        assert _qc(_cert(app, csr_id)) is None

    def test_protocol_bridge_adds_nothing(self, app, cps_ca, make_template):
        """EST, WSTEP and mTLS sign through the bridge, which hands over no
        qualification template even when WSTEP matched one."""
        from services.ca.ca_service import CAService
        csr = _csr('qc-bridge.example.test')
        with app.app_context():
            ca = db.session.get(CA, cps_ca['id'])
            pem, *_ = CAService.sign_csr_from_crypto(
                ca, csr, validity_days=30, source='wstep', policy_template_id=make_template())
        cert = x509.load_pem_x509_certificate(pem if isinstance(pem, bytes) else pem.encode())
        assert _qc(cert) is None
        assert _policy_oids(cert) == [CPS_OID]


class TestApproval:
    def test_approved_issuance_carries_the_template(self, app, cps_ca, make_template):
        from tests.test_approval_template_issuance import _issue_from_request
        cert, _ = _issue_from_request(app, None, {
            'cn': 'qc-approval.example.test', 'ca_id': cps_ca['id'], 'cert_type': 'server',
            'template_id': make_template()})
        _assert_qualified(cert)


class TestScep:
    def test_profile_template(self, app, cps_ca, make_template):
        from tests.test_scep_defaults_and_template_ekus import _csr as scep_csr, _issue
        with app.app_context():
            tpl = db.session.get(CertificateTemplate, make_template())
            cert = _issue(app, cps_ca['id'], scep_csr('qc-scep.example.test'), template=tpl,
                          txn='scep-qc')
        _assert_qualified(cert)

    def test_no_template_no_qc(self, app, cps_ca):
        from tests.test_scep_defaults_and_template_ekus import _csr as scep_csr, _issue
        cert = _issue(app, cps_ca['id'], scep_csr('qc-scep-none.example.test'), txn='scep-qc-none')
        assert _qc(cert) is None
        assert _policy_oids(cert) == [CPS_OID]


class TestRenewal:
    def test_renewal_keeps_qc_and_template_policies(self, app, auth_client, cps_ca, make_template):
        from services.cert.renewal import renew_certificate_in_place
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'qc-renew.example.test', 'ca_id': cps_ca['id'], 'template_id': make_template()})
        assert r.status_code in (200, 201), r.get_json()
        cert_id = r.get_json()['data']['id']
        with app.app_context():
            renew_certificate_in_place(db.session.get(Certificate, cert_id), username='test')
        _assert_qualified(_cert(app, cert_id))

    def test_renewal_follows_the_ca_cps_change(self, app, auth_client, cps_ca, make_template):
        from services.cert.renewal import renew_certificate_in_place
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'qc-renew2.example.test', 'ca_id': cps_ca['id'], 'template_id': make_template()})
        cert_id = r.get_json()['data']['id']
        with app.app_context():
            ca = db.session.get(CA, cps_ca['id'])
            ca.cps_oid = '1.3.6.1.4.1.99999.2'
            db.session.commit()
            renew_certificate_in_place(db.session.get(Certificate, cert_id), username='test')
        assert _policy_oids(_cert(app, cert_id)) == ['1.3.6.1.4.1.99999.2'] + POLICIES

    def test_renewal_drops_a_policy_the_template_no_longer_lists(self, app, auth_client, cps_ca,
                                                                 make_template):
        from services.cert.renewal import renew_certificate_in_place
        tpl_id = make_template()
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'qc-renew4.example.test', 'ca_id': cps_ca['id'], 'template_id': tpl_id})
        cert_id = r.get_json()['data']['id']
        with app.app_context():
            tpl = db.session.get(CertificateTemplate, tpl_id)
            ext = json.loads(tpl.extensions_template)
            ext['certificate_policies'] = []
            tpl.extensions_template = json.dumps(ext)
            db.session.commit()
            renew_certificate_in_place(db.session.get(Certificate, cert_id), username='test')
        assert _policy_oids(_cert(app, cert_id)) == [CPS_OID]

    def test_plain_certificate_renews_without_extras(self, app, auth_client, cps_ca):
        from services.cert.renewal import renew_certificate_in_place
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'qc-renew3.example.test', 'ca_id': cps_ca['id']})
        cert_id = r.get_json()['data']['id']
        with app.app_context():
            renew_certificate_in_place(db.session.get(Certificate, cert_id), username='test')
        cert = _cert(app, cert_id)
        assert _qc(cert) is None
        assert _policy_oids(cert) == [CPS_OID]


class TestDisplay:
    def _issued(self, app, auth_client, cps_ca, make_template):
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'qc-display.example.test', 'ca_id': cps_ca['id'], 'template_id': make_template()})
        return r.get_json()['data']['id']

    def test_parse_certificate_extensions(self, app, auth_client, cps_ca, make_template):
        from utils.cert_extensions import parse_certificate_extensions
        cert_id = self._issued(app, auth_client, cps_ca, make_template)
        with app.app_context():
            pem = base64.b64decode(db.session.get(Certificate, cert_id).crt).decode()
        ext = parse_certificate_extensions(pem)['qc_statements']
        assert ext['critical'] is False
        assert {k: ext[k] for k in QC} == QC

    def test_parsing_mixin_names_it_instead_of_unknown_oid(self, app, auth_client, cps_ca,
                                                           make_template):
        from services.trust_store.parsing_mixin import ParsingMixin
        cert_id = self._issued(app, auth_client, cps_ca, make_template)
        with app.app_context():
            pem = base64.b64decode(db.session.get(Certificate, cert_id).crt).decode()
        details = ParsingMixin.parse_certificate_details(pem.encode())
        assert 'qcStatements' in details['extensions']
        assert details['extensions']['qcStatements']['compliance'] is True
        assert not any(k.startswith('Unknown OID (1.3.6.1.5.5.7.1.3)') for k in details['extensions'])

    def test_a_certificate_issued_elsewhere_is_decoded_too(self):
        from tests.test_qc_statements_module import FULL, _cert as foreign_cert
        from utils import qc_statements
        from utils.cert_extensions import parse_certificate_extensions
        pem = foreign_cert(qc_statements.qc_statements_extension({'qc_statements': FULL})) \
            .public_bytes(serialization.Encoding.PEM).decode()
        assert {k: parse_certificate_extensions(pem)['qc_statements'][k] for k in FULL} == FULL
