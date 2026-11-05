"""Custom X.509 extensions (#437): the extensions without a section, on certificate, CA and CSR details."""
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from tests.test_csr_sign_extra_names import _upload
from tests.test_custom_extensions import DER_B, OID_B, _SEQ


# ── display ─────────────────────────────────────────────────────────────────

def _self_signed(*extensions):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'display.example.test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
               .serial_number(x509.random_serial_number()).not_valid_before(now)
               .not_valid_after(now + datetime.timedelta(days=1)))
    for ext, critical in extensions:
        builder = builder.add_extension(ext, critical=critical)
    return builder.sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM).decode()


class TestDisplay:
    def test_detail_lists_the_extensions_without_a_section(self, app, auth_client, create_ca):
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'custom-display.example.test', 'ca_id': ca['id'], 'ocsp_must_staple': True,
            'custom_extensions': [{'oid': OID_B, 'critical': True, 'value': DER_B}]})
        cert_id = r.get_json()['data']['id']
        ext = auth_client.get(f'/api/v2/certificates/{cert_id}').get_json()['data']['extensions']
        assert {'oid': OID_B, 'name': None, 'critical': True, 'value_hex': DER_B} in ext['other_extensions']
        tls = next(e for e in ext['other_extensions'] if e['oid'] == '1.3.6.1.5.5.7.1.24')
        assert tls['name'] == 'TLSFeature' and tls['value_hex'] == '3003020105'
        shown = {e['oid'] for e in ext['other_extensions']}
        assert not shown & {'2.5.29.19', '2.5.29.15', '2.5.29.17', '2.5.29.14', '2.5.29.35'}

    def test_names_from_the_internal_table_and_qc_fallback(self):
        from utils.cert_extensions import parse_certificate_extensions
        pem = _self_signed(
            (x509.UnrecognizedExtension(x509.ObjectIdentifier('1.3.6.1.4.1.311.21.10'), b'\x30\x00'), False),
            (x509.UnrecognizedExtension(x509.ObjectIdentifier('1.3.6.1.5.5.7.1.3'), b'\x05\x00'), False))
        other = {e['oid']: e for e in parse_certificate_extensions(pem)['other_extensions']}
        assert other['1.3.6.1.4.1.311.21.10']['name'] == 'msApplicationPolicies'
        # A qcStatements value UCM cannot decode is still shown, raw
        assert other['1.3.6.1.5.5.7.1.3'] == {'oid': '1.3.6.1.5.5.7.1.3', 'name': 'qcStatements',
                                              'critical': False, 'value_hex': '0500'}

    def test_csr_detail(self, auth_client):
        key = ec.generate_private_key(ec.SECP256R1())
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'custom-csr.example.test')]))
               .add_extension(x509.UnrecognizedExtension(x509.ObjectIdentifier(OID_B), bytes.fromhex(DER_B)),
                              critical=False)
               .add_extension(x509.SubjectAlternativeName([x509.DNSName('custom-csr.example.test')]),
                              critical=False)
               .sign(key, hashes.SHA256()))
        detail = auth_client.get(f'/api/v2/csrs/{_upload(auth_client, csr)}').get_json()['data']
        assert detail['other_extensions'] == [
            {'oid': OID_B, 'name': None, 'critical': False, 'value_hex': DER_B}]

    def test_ca_detail(self, auth_client, create_ca):
        ca = create_ca(cn=f'Custom ext CA {next(_SEQ)}')
        key = ec.generate_private_key(ec.SECP256R1())
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'Custom Sub {next(_SEQ)}')]))
               .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
               .sign(key, hashes.SHA256()))
        r = auth_client.post(f'/api/v2/csrs/{_upload(auth_client, csr)}/sign', json={
            'ca_id': ca['id'], 'validity_days': 30, 'cert_type': 'intermediate_ca',
            'custom_extensions': [{'oid': OID_B, 'value': DER_B}]})
        assert r.status_code == 200, r.get_json()
        detail = auth_client.get(f"/api/v2/cas/{r.get_json()['data']['id']}").get_json()['data']
        assert {'oid': OID_B, 'name': None, 'critical': False, 'value_hex': DER_B} in \
            detail['extensions']['other_extensions']

    def test_nothing_extra_on_a_plain_certificate(self):
        from utils.cert_extensions import parse_certificate_extensions
        pem = _self_signed((x509.BasicConstraints(ca=False, path_length=None), True))
        assert 'other_extensions' not in parse_certificate_extensions(pem)
