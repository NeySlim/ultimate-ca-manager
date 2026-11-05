"""Custom X.509 extensions (#437) on every issuance path that reads a template, and renewal."""
import base64
import types

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import CA, Certificate, CertificateTemplate, db
from tests.test_acme_profile_template import _clear_profiles, _install_profiles
from tests.test_csr_sign_extra_names import _csr, _upload
from tests.test_custom_extensions import (  # noqa: F401 (fixture)
    DER_A, DER_B, OID_A, OID_B, _SEQ, _cert, _set_template_extensions, _value, make_template)


# ── issuance ────────────────────────────────────────────────────────────────

class TestIssueForm:
    def test_template_extensions_land(self, app, auth_client, create_ca, make_template):
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'custom-form.example.test', 'ca_id': ca['id'], 'template_id': make_template()})
        assert r.status_code == 201, r.get_json()
        assert _value(_cert(app, r.get_json()['data']['id']), OID_A) == (DER_A, False)

    def test_request_overrides_and_adds(self, app, auth_client, create_ca, make_template):
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'custom-override.example.test', 'ca_id': ca['id'], 'template_id': make_template(),
            'custom_extensions': [{'oid': OID_A, 'critical': True, 'value': '0500'},
                                  {'oid': OID_B, 'value': DER_B}]})
        assert r.status_code == 201, r.get_json()
        cert = _cert(app, r.get_json()['data']['id'])
        assert _value(cert, OID_A) == ('0500', True)
        assert _value(cert, OID_B) == (DER_B, False)

    def test_without_template(self, app, auth_client, create_ca):
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'custom-plain.example.test', 'ca_id': ca['id'],
            'custom_extensions': [{'oid': OID_B, 'value': DER_B}]})
        assert r.status_code == 201, r.get_json()
        cert = _cert(app, r.get_json()['data']['id'])
        assert _value(cert, OID_B) == (DER_B, False) and _value(cert, OID_A) is None

    def test_refused_before_anything_is_issued(self, app, auth_client, create_ca):
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        with app.app_context():
            before = Certificate.query.count()
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'custom-refused.example.test', 'ca_id': ca['id'],
            'custom_extensions': [{'oid': '2.5.29.19', 'value': '3000'}]})
        assert r.status_code == 400 and 'basicConstraints' in r.get_json()['message']
        with app.app_context():
            assert Certificate.query.count() == before

    def test_a_template_holding_an_invalid_list_refuses(self, app, auth_client, create_ca, make_template):
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        tpl_id = make_template([{'oid': '2.5.29.19', 'value': '3000'}])
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'custom-badtpl.example.test', 'ca_id': ca['id'], 'template_id': tpl_id})
        assert r.status_code == 400 and 'invalid custom extensions' in r.get_json()['message']

    def test_approved_request_carries_both(self, app, create_ca, make_template):
        from tests.test_approval_template_issuance import _issue_from_request
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        cert, _ = _issue_from_request(app, None, {
            'cn': 'custom-approval.example.test', 'ca_id': ca['id'], 'cert_type': 'server',
            'template_id': make_template(),
            'custom_extensions': [{'oid': OID_B, 'critical': True, 'value': DER_B}]})
        assert _value(cert, OID_A) == (DER_A, False)
        assert _value(cert, OID_B) == (DER_B, True)


class TestSignCsr:
    def test_sign_csr_form(self, app, auth_client, create_ca, make_template):
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        csr_id = _upload(auth_client, _csr('custom-sign.example.test'))
        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={
            'ca_id': ca['id'], 'validity_days': 30, 'template_id': make_template(),
            'custom_extensions': [{'oid': OID_A, 'critical': True, 'value': DER_B}]})
        assert r.status_code == 200, r.get_json()
        assert _value(_cert(app, csr_id), OID_A) == (DER_B, True)

    def test_sign_csr_refusal(self, app, auth_client, create_ca):
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        csr_id = _upload(auth_client, _csr('custom-sign-bad.example.test'))
        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={
            'ca_id': ca['id'], 'validity_days': 30,
            'custom_extensions': [{'oid': '1.3.6.1.5.5.7.1.1', 'value': '3000'}]})
        assert r.status_code == 400 and 'authorityInfoAccess' in r.get_json()['message']
        with app.app_context():
            assert not db.session.get(Certificate, csr_id).crt

    def test_bulk_sign_applies_the_template(self, app, auth_client, create_ca, make_template):
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        csr_id = _upload(auth_client, _csr('custom-bulk.example.test'))
        r = auth_client.post('/api/v2/csrs/bulk/sign', json={
            'ids': [csr_id], 'ca_id': ca['id'], 'validity_days': 30, 'template_id': make_template()})
        assert r.status_code == 200 and r.get_json()['data']['success'] == [csr_id], r.get_json()
        assert _value(_cert(app, csr_id), OID_A) == (DER_A, False)

    def test_a_csr_cannot_bring_its_own(self, app, auth_client, create_ca):
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        key = ec.generate_private_key(ec.SECP256R1())
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'custom-own.example.test')]))
               .add_extension(x509.UnrecognizedExtension(x509.ObjectIdentifier(OID_B), bytes.fromhex(DER_B)),
                              critical=False)
               .sign(key, hashes.SHA256()))
        csr_id = _upload(auth_client, csr)
        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={'ca_id': ca['id'], 'validity_days': 30})
        assert r.status_code == 200, r.get_json()
        assert _value(_cert(app, csr_id), OID_B) is None

    def test_intermediate_takes_the_request_list_only(self, app, auth_client, create_ca, make_template):
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        key = ec.generate_private_key(ec.SECP256R1())
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'Custom Sub {next(_SEQ)}')]))
               .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
               .sign(key, hashes.SHA256()))
        csr_id = _upload(auth_client, csr)
        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={
            'ca_id': ca['id'], 'validity_days': 30, 'cert_type': 'intermediate_ca',
            'template_id': make_template(), 'custom_extensions': [{'oid': OID_B, 'value': DER_B}]})
        assert r.status_code == 200, r.get_json()
        sub = r.get_json()['data']
        with app.app_context():
            row = db.session.get(CA, sub['id'])
            cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        assert _value(cert, OID_B) == (DER_B, False) and _value(cert, OID_A) is None

    def test_acme_profile_template(self, app, auth_client, create_ca, make_template):
        from services.acme import AcmeService
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        tpl_id = make_template()
        _install_profiles(app, {'custom': {'validity_days': 30, 'template_id': tpl_id}})
        try:
            pem = _csr('custom-acme.example.test').public_bytes(serialization.Encoding.PEM).decode()
            with app.app_context():
                ca_refid = db.session.get(CA, ca['id']).refid
                order = types.SimpleNamespace(order_id='custom-ext-order', profile='custom')
                ok, cert_id, err = AcmeService(base_url='http://localhost')._sign_certificate_with_ca(
                    order, pem, ca_refid)
                assert ok, err
            assert _value(_cert(app, cert_id), OID_A) == (DER_A, False)
        finally:
            _clear_profiles(app)

    def test_wstep_bridge_applies_the_matched_template(self, app, create_ca, make_template):
        from services.ca.ca_service import CAService
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        tpl_id = make_template()
        with app.app_context():
            pem, *_ = CAService.sign_csr_from_crypto(
                db.session.get(CA, ca['id']), _csr('custom-wstep.example.test'), validity_days=30,
                source='wstep', policy_template_id=tpl_id)
            plain, *_ = CAService.sign_csr_from_crypto(
                db.session.get(CA, ca['id']), _csr('custom-est.example.test'), validity_days=30, source='est')
        load = lambda p: x509.load_pem_x509_certificate(p if isinstance(p, bytes) else p.encode())
        assert _value(load(pem), OID_A) == (DER_A, False)
        assert _value(load(plain), OID_A) is None


class TestScep:
    def test_profile_template(self, app, create_ca, make_template):
        from tests.test_scep_defaults_and_template_ekus import _csr as scep_csr, _issue
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        with app.app_context():
            tpl = db.session.get(CertificateTemplate, make_template())
            cert = _issue(app, ca['id'], scep_csr('custom-scep.example.test'), template=tpl,
                          txn='scep-custom-ext')
        assert _value(cert, OID_A) == (DER_A, False)


class TestRenewal:
    def _issue(self, auth_client, create_ca, tpl_id, **body):
        ca = create_ca(cn=f'Custom ext renew CA {next(_SEQ)}')
        r = auth_client.post('/api/v2/certificates', json={
            'cn': f'custom-renew-{next(_SEQ)}.example.test', 'ca_id': ca['id'], 'template_id': tpl_id,
            **body})
        assert r.status_code == 201, r.get_json()
        return r.get_json()['data']['id']

    def _renew(self, app, cert_id):
        from services.cert.renewal import renew_certificate_in_place
        with app.app_context():
            renew_certificate_in_place(db.session.get(Certificate, cert_id), username='test')
        return _cert(app, cert_id)

    def test_request_extensions_are_carried(self, app, auth_client, create_ca, make_template):
        cert_id = self._issue(auth_client, create_ca, make_template(), custom_extensions=[
            {'oid': OID_B, 'critical': True, 'value': DER_B}])
        before = _cert(app, cert_id).serial_number
        cert = self._renew(app, cert_id)
        assert cert.serial_number != before
        assert _value(cert, OID_A) == (DER_A, False)
        assert _value(cert, OID_B) == (DER_B, True)

    def test_the_current_template_replaces_and_adds(self, app, auth_client, create_ca, make_template):
        tpl_id = make_template()
        cert_id = self._issue(auth_client, create_ca, tpl_id, custom_extensions=[
            {'oid': OID_B, 'value': DER_B}])
        _set_template_extensions(app, tpl_id, [{'oid': OID_A, 'critical': True, 'value': '0500'},
                                              {'oid': '1.3.6.1.4.1.55555.1.3', 'value': DER_B}])
        cert = self._renew(app, cert_id)
        assert _value(cert, OID_A) == ('0500', True)
        assert _value(cert, OID_B) == (DER_B, False)
        assert _value(cert, '1.3.6.1.4.1.55555.1.3') == (DER_B, False)
