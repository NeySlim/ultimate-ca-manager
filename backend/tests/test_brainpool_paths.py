"""Brainpool (RFC 5639) is issued end to end outside FIPS mode.

Artefacts are checked by OpenSSL, not only by pyca. The registry digest
(sha384 for BP384, sha512 for BP512) is the default wherever one is chosen.
"""
import base64
import json
import shutil
import subprocess

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db

OPENSSL = shutil.which('openssl')
CURVES = {'EC-BP256': ec.BrainpoolP256R1, 'EC-BP384': ec.BrainpoolP384R1, 'EC-BP512': ec.BrainpoolP512R1}
DIGESTS = {'EC-BP256': hashes.SHA256, 'EC-BP384': hashes.SHA384, 'EC-BP512': hashes.SHA512}


def _pem(obj):
    return obj.public_bytes(serialization.Encoding.PEM)


def _openssl(tmp_path, *args, **files):
    assert OPENSSL, 'openssl is required'
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    out = subprocess.run([OPENSSL, *args], capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout


def _row_cert(row):
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


def _bp_csr(cn, label='EC-BP256'):
    key = ec.generate_private_key(CURVES[label]())
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    ).add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False
                    ).sign(key, DIGESTS[label]())
    return key, csr


def _label(cert):
    return {v: k for k, v in CURVES.items()}[type(cert.public_key().curve)]


def _curve(cert):
    return cert.public_key().curve.name


def _post(auth_client, url, body):
    return auth_client.post(url, content_type='application/json', data=json.dumps(body))


@pytest.fixture(scope='module')
def bp384_root(create_ca):
    return create_ca(cn='Brainpool paths root', keyAlgo='EC-BP384', keySize=None, hashAlgorithm='auto')


@pytest.fixture
def root_cert(app, bp384_root):
    with app.app_context():
        return _row_cert(db.session.get(CA, bp384_root['id']))


def _check_chain(leaf, root, tmp_path, inter=None):
    issuer = inter or root
    leaf.verify_directly_issued_by(issuer)
    # The registry digest of the signing key, where nothing asked for another
    assert type(leaf.signature_hash_algorithm) is DIGESTS[_label(issuer)]
    files = {'leaf.pem': _pem(leaf), 'root.pem': _pem(root)}
    args = ['verify', '-CAfile', 'root.pem']
    if inter is not None:
        files['inter.pem'] = _pem(inter)
        args += ['-untrusted', 'inter.pem']
    _openssl(tmp_path, *args, 'leaf.pem', **files)


def test_root_ca_uses_the_registry_digest(root_cert, tmp_path):
    assert _curve(root_cert) == 'brainpoolP384r1'
    assert isinstance(root_cert.signature_hash_algorithm, hashes.SHA384)
    _openssl(tmp_path, 'verify', '-CAfile', 'root.pem', 'root.pem', **{'root.pem': _pem(root_cert)})


def _ca_via_api(auth_client, label, parent=None, cn=None):
    body = {'type': 'intermediate' if parent else 'root', 'commonName': cn or f'BP {label} {"sub" if parent else "root"}',
            'keyAlgo': label, 'keySize': None, 'validityYears': 2, 'hashAlgorithm': 'auto'}
    if parent:
        body['parentCAId'] = parent['id']
    r = _post(auth_client, '/api/v2/cas', body)
    assert r.status_code == 201, r.get_json()
    return r.get_json()['data']


@pytest.mark.parametrize('root_label,leaf_label', [('EC-BP384', 'EC-BP256'), ('EC-BP256', 'EC-BP384'),
                                                    ('EC-BP512', 'EC-BP512')])
def test_intermediate_ca_and_leaf_chain(app, auth_client, root_label, leaf_label, tmp_path):
    root = _ca_via_api(auth_client, root_label)
    sub = _ca_via_api(auth_client, leaf_label, parent=root)
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': f'leaf-{root_label}-{leaf_label}.example.test', 'ca_id': sub['id'],
        'key_type': 'ec', 'curve': leaf_label, 'validity_days': 30})
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        root_c = _row_cert(db.session.get(CA, root['id']))
        sub_c = _row_cert(db.session.get(CA, sub['id']))
        leaf = _row_cert(db.session.get(Certificate, r.get_json()['data']['id']))
    assert type(sub_c.signature_hash_algorithm) is DIGESTS[leaf_label]
    assert type(sub_c.public_key().curve) is CURVES[leaf_label]
    assert type(leaf.public_key().curve) is CURVES[leaf_label]
    sub_c.verify_directly_issued_by(root_c)
    _check_chain(leaf, root_c, tmp_path, inter=sub_c)


@pytest.mark.parametrize('spelling', ['EC-BP256', 'brainpoolP256r1', 'BP-256', 'EC-brainpoolP256r1'])
def test_form_leaf_accepts_every_spelling(app, auth_client, bp384_root, root_cert, spelling, tmp_path):
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': 'spelling.example.test', 'ca_id': bp384_root['id'], 'key_type': 'ec', 'curve': spelling,
        'validity_days': 30})
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        row = db.session.get(Certificate, r.get_json()['data']['id'])
        leaf = _row_cert(row)
        assert row.key_algo == 'EC brainpoolP256r1'
    _check_chain(leaf, root_cert, tmp_path)


def test_sign_csr_and_bulk(app, auth_client, bp384_root, root_cert, tmp_path):
    ids = []
    labels = ('EC-BP256', 'EC-BP384', 'EC-BP512')
    for i, label in enumerate(labels):
        _, csr = _bp_csr(f'csr{i}.example.test', label)
        r = _post(auth_client, '/api/v2/csrs/upload', {'pem': _pem(csr).decode(), 'name': f'bp-{label}'})
        assert r.status_code in (200, 201), r.get_json()
        ids.append(r.get_json()['data']['id'])
    r = _post(auth_client, f'/api/v2/csrs/{ids[0]}/sign', {'ca_id': bp384_root['id'], 'validity_days': 30})
    assert r.status_code in (200, 201), r.get_json()
    r = _post(auth_client, '/api/v2/csrs/bulk/sign', {'ids': ids[1:], 'ca_id': bp384_root['id'], 'validity_days': 30})
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        for csr_id, label in zip(ids, labels):
            leaf = _row_cert(db.session.get(Certificate, csr_id))
            assert type(leaf.public_key().curve) is CURVES[label]
            _check_chain(leaf, root_cert, tmp_path)


def test_in_place_renewal_keeps_the_curve(app, auth_client, bp384_root, root_cert, tmp_path):
    from services.cert.renewal import renew_certificate_in_place
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': 'renew.example.test', 'ca_id': bp384_root['id'], 'key_type': 'ec', 'curve': 'EC-BP512',
        'validity_days': 30})
    assert r.status_code == 201, r.get_json()
    row_id = r.get_json()['data']['id']
    with app.app_context():
        renew_certificate_in_place(db.session.get(Certificate, row_id), username='admin')
        db.session.commit()
        leaf = _row_cert(db.session.get(Certificate, row_id))
    assert _curve(leaf) == 'brainpoolP512r1'
    _check_chain(leaf, root_cert, tmp_path)


def test_tsa_signer_certificate(app, bp384_root, root_cert, tmp_path):
    from services import tsa_signer_cert
    with app.app_context():
        issued = tsa_signer_cert.issue_tsa_signer_certificate(
            ca=db.session.get(CA, bp384_root['id']), cn='bp-tsa.example.test',
            key_type='ec', curve='EC-BP256')
        leaf = _row_cert(issued)
    assert _curve(leaf) == 'brainpoolP256r1'
    _check_chain(leaf, root_cert, tmp_path)



def test_a_brainpool_tsa_signer_stamps_tokens_openssl_verifies(app, bp384_root, root_cert, tmp_path):
    import hashlib
    from asn1crypto import tsp
    from services import tsa_signer_cert
    from services.tsa_service import TSAService, _load_signer_certificate
    with app.app_context():
        issued = tsa_signer_cert.issue_tsa_signer_certificate(
            ca=db.session.get(CA, bp384_root['id']), cn='bp-tsa-token.example.test',
            key_type='ec', curve='EC-BP256')
        _, cert, key, chain = _load_signer_certificate(issued.refid)
    data = b'brainpool timestamp'
    query = tsp.TimeStampReq({
        'version': 1, 'cert_req': True,
        'message_imprint': {'hash_algorithm': {'algorithm': 'sha256'},
                            'hashed_message': hashlib.sha256(data).digest()}}).dump()
    der, http = TSAService(cert, key, chain_certs=chain).process_request(query)
    assert http == 200
    assert tsp.TimeStampResp.load(der)['status']['status'].native == 'granted'
    _openssl(tmp_path, 'ts', '-verify', '-in', 'r.tsr', '-data', 'data.bin', '-CAfile', 'ca.pem',
             '-untrusted', 'signer.pem',
             **{'r.tsr': der, 'data.bin': data, 'ca.pem': _pem(root_cert), 'signer.pem': _pem(cert)})

def test_crl_of_a_brainpool_ca_defaults_to_the_registry_digest(app, bp384_root, root_cert, tmp_path):
    from services.crl_service import CRLService
    with app.app_context():
        pem = CRLService.generate_crl(bp384_root['id']).crl_pem
    crl = x509.load_pem_x509_crl(pem.encode())
    assert crl.is_signature_valid(root_cert.public_key())
    assert isinstance(crl.signature_hash_algorithm, hashes.SHA384)
    _openssl(tmp_path, 'crl', '-in', 'crl.pem', '-CAfile', 'ca.pem', '-noout',
             **{'crl.pem': pem.encode(), 'ca.pem': _pem(root_cert)})


def _leaf_row(auth_client, ca_id, cn, curve='EC-BP256', **extra):
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': cn, 'ca_id': ca_id, 'key_type': 'ec', 'curve': curve, 'validity_days': 30, **extra})
    assert r.status_code == 201, r.get_json()
    return r.get_json()['data']['id']


def _ask_ocsp(app, client, ca_id, tmp_path, ca_cert, leaf):
    """An OpenSSL-built request answered by the /ocsp route, then verified by OpenSSL."""
    from api.ocsp_routes import OCSP_REQUEST_TYPE
    with app.app_context():
        db.session.get(CA, ca_id).ocsp_enabled = True
        db.session.commit()
    _openssl(tmp_path, 'ocsp', '-issuer', 'ca.pem', '-cert', 'leaf.pem', '-reqout', 'req.der', '-no_nonce',
             **{'ca.pem': _pem(ca_cert), 'leaf.pem': _pem(leaf)})
    resp = client.post('/ocsp', data=(tmp_path / 'req.der').read_bytes(), content_type=OCSP_REQUEST_TYPE)
    assert resp.status_code == 200
    (tmp_path / 'resp.der').write_bytes(resp.data)
    out = subprocess.run([OPENSSL, 'ocsp', '-issuer', 'ca.pem', '-cert', 'leaf.pem', '-respin', 'resp.der',
                          '-CAfile', 'ca.pem'], capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr
    assert 'Response verify OK' in out.stderr and 'leaf.pem: good' in out.stdout
    return resp.data


def test_ocsp_answer_of_a_brainpool_ca_verifies(app, client, auth_client, bp384_root, root_cert, tmp_path):
    from cryptography.x509 import ocsp
    leaf_id = _leaf_row(auth_client, bp384_root['id'], 'ocsp-ca.example.test')
    with app.app_context():
        leaf = _row_cert(db.session.get(Certificate, leaf_id))
    der = _ask_ocsp(app, client, bp384_root['id'], tmp_path, root_cert, leaf)
    assert isinstance(ocsp.load_der_ocsp_response(der).signature_hash_algorithm, hashes.SHA384)


def test_delegated_responder_and_its_renewal(app, client, auth_client, bp384_root, root_cert, tmp_path):
    from cryptography.x509 import ocsp
    from models import SystemConfig
    from services import ocsp_responder_renewal
    responder_id = _leaf_row(auth_client, bp384_root['id'], 'bp-responder.example.test', 'EC-BP256',
                             cert_type='custom', extra_ekus=['OCSPSigning'])
    leaf_id = _leaf_row(auth_client, bp384_root['id'], 'ocsp-delegated.example.test')
    with app.app_context():
        db.session.add(SystemConfig(key=f'ocsp_responder_cert_{bp384_root["id"]}', value=str(responder_id)))
        db.session.commit()
        ocsp_responder_renewal._renew_responder_cert(db.session.get(CA, bp384_root['id']),
                                                     db.session.get(Certificate, responder_id))
        db.session.commit()
        renewed = _row_cert(db.session.get(Certificate, responder_id))
        leaf = _row_cert(db.session.get(Certificate, leaf_id))
    assert _curve(renewed) == 'brainpoolP256r1'
    renewed.verify_directly_issued_by(root_cert)
    der = _ask_ocsp(app, client, bp384_root['id'], tmp_path, root_cert, leaf)
    answer = ocsp.load_der_ocsp_response(der)
    assert answer.certificates and answer.certificates[0].serial_number == renewed.serial_number
    assert isinstance(answer.signature_hash_algorithm, hashes.SHA256)


# ---------------------------------------------------------------------------
# Protocols: EST, ACME server, SCEP, WSTEP
# ---------------------------------------------------------------------------

def _set_config(key, value):
    from models.system_config import SystemConfig
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


@pytest.fixture
def protocol_config(app, bp384_root):
    """EST and WSTEP pointed at the Brainpool root, restored afterwards."""
    from models.system_config import SystemConfig
    keys = ('est_enabled', 'est_ca_refid', 'est_username', 'est_password', 'est_validity_days',
            'wstep_enabled', 'wstep_ca_refid', 'wstep_username', 'wstep_password', 'wstep_validity_days')
    with app.app_context():
        previous = {k: (r.value if (r := SystemConfig.query.filter_by(key=k).first()) else None) for k in keys}
        refid = db.session.get(CA, bp384_root['id']).refid
        for prefix in ('est', 'wstep'):
            _set_config(f'{prefix}_enabled', 'true')
            _set_config(f'{prefix}_ca_refid', refid)
            _set_config(f'{prefix}_username', 'bp-user')
            _set_config(f'{prefix}_password', 'bp-password')
            _set_config(f'{prefix}_validity_days', '30')
    yield
    with app.app_context():
        for k, v in previous.items():
            row = SystemConfig.query.filter_by(key=k).first()
            if v is None and row is not None:
                db.session.delete(row)
            elif v is not None and row is None:
                db.session.add(SystemConfig(key=k, value=v))
            elif row is not None:
                row.value = v
        db.session.commit()


def _basic():
    token = base64.b64encode(b'bp-user:bp-password').decode()
    return {'Authorization': f'Basic {token}'}


@pytest.mark.parametrize('label', ['EC-BP256', 'EC-BP384', 'EC-BP512'])
def test_est_simpleenroll(app, client, protocol_config, root_cert, label, tmp_path):
    from cryptography.hazmat.primitives.serialization import pkcs7
    _, csr = _bp_csr(f'est-{label.lower()}.example.test', label)
    resp = client.post('/.well-known/est/simpleenroll', data=base64.b64encode(csr.public_bytes(
        serialization.Encoding.DER)), headers=_basic(), content_type='application/pkcs10')
    assert resp.status_code == 200, resp.data
    leaf = pkcs7.load_der_pkcs7_certificates(base64.b64decode(resp.data))[0]
    assert type(leaf.public_key().curve) is CURVES[label]
    _check_chain(leaf, root_cert, tmp_path)


@pytest.mark.parametrize('label', ['EC-BP256', 'EC-BP384', 'EC-BP512'])
def test_acme_finalize_with_a_brainpool_csr(app, monkeypatch, bp384_root, root_cert, label, tmp_path):
    from services.acme.acme_service import AcmeService
    from tests.test_acme_profile_template import TestFinalizeWithBoundTemplate
    from utils import caa_checker
    with app.app_context():
        refid = db.session.get(CA, bp384_root['id']).refid
        order = TestFinalizeWithBoundTemplate._order(None)
        service = AcmeService(base_url='http://localhost')
        monkeypatch.setattr(caa_checker, 'check_caa_for_domains', lambda *a, **k: (True, 'allowed'))
        monkeypatch.setattr(service, '_resolve_ca_for_domains', lambda _d: refid)
        _, csr = _bp_csr('web.example.com', label)
        service.begin_order_processing(order)
        service._finalizing_order_id = order.order_id
        ok, error = service.finalize_order(order.order_id, _pem(csr).decode())
        service._finalizing_order_id = None
        assert ok, error
        db.session.refresh(order)
        leaf = _row_cert(db.session.get(Certificate, order.certificate_id))
    assert type(leaf.public_key().curve) is CURVES[label]
    _check_chain(leaf, root_cert, tmp_path)


def _rst(csr):
    from tests.test_wstep_issue import _build_rst
    return _build_rst(csr)


@pytest.mark.parametrize('label', ['EC-BP256', 'EC-BP512'])
def test_wstep_issue(app, client, protocol_config, root_cert, label, tmp_path):
    from tests.test_wstep_issue import ISSUE_URL, _issued_cert_from_rstr
    _, csr = _bp_csr(f'wstep-{label.lower()}.example.test', label)
    resp = client.post(ISSUE_URL, data=_rst(csr),
                       headers={'Authorization': 'Basic ' + base64.b64encode(b'bp-user:bp-password').decode()})
    assert resp.status_code == 200, resp.data
    leaf = _issued_cert_from_rstr(resp.data)
    assert type(leaf.public_key().curve) is CURVES[label]
    _check_chain(leaf, root_cert, tmp_path)


def _signed_renewal_rst(signing_cert, signing_key, csr):
    """A WS-Security signed RST (ECDSA-SHA256 over the Body) like test_wstep_renew builds for RSA."""
    import xmlsec
    from lxml import etree
    from services.wstep.soap_envelope import ADDRESSING_NS, SOAP_NS, WSSE_NS, WST_NS, WSU_NS
    envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap={
        's': SOAP_NS, 'a': ADDRESSING_NS, 'wst': WST_NS, 'wsse': WSSE_NS, 'wsu': WSU_NS})
    header = etree.SubElement(envelope, '{%s}Header' % SOAP_NS)
    etree.SubElement(header, '{%s}MessageID' % ADDRESSING_NS).text = 'urn:uuid:bp-renew'
    security = etree.SubElement(header, '{%s}Security' % WSSE_NS)
    etree.SubElement(security, '{%s}BinarySecurityToken' % WSSE_NS, EncodingType='base64', ValueType=(
        'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3')
    ).text = base64.b64encode(signing_cert.public_bytes(serialization.Encoding.DER)).decode()
    body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
    body.set('{%s}Id' % WSU_NS, 'body-1')
    rst = etree.SubElement(body, '{%s}RequestSecurityToken' % WST_NS)
    etree.SubElement(rst, '{%s}BinarySecurityToken' % WSSE_NS, EncodingType='base64', ValueType=(
        'http://schemas.microsoft.com/windows/pki/2009/01/enrollment#PKCS10')
    ).text = base64.b64encode(csr.public_bytes(serialization.Encoding.DER)).decode()
    sig = xmlsec.template.create(security, xmlsec.constants.TransformExclC14N,
                                 xmlsec.constants.TransformEcdsaSha256)
    security.append(sig)
    ref = xmlsec.template.add_reference(sig, xmlsec.constants.TransformSha256, uri='#body-1')
    xmlsec.template.add_transform(ref, xmlsec.constants.TransformExclC14N)
    ctx = xmlsec.SignatureContext()
    ctx.register_id(body, id_attr='Id', id_ns=WSU_NS)
    ctx.key = xmlsec.Key.from_memory(signing_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
        xmlsec.constants.KeyDataFormatPem)
    ctx.sign(sig)
    return etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')


def test_wstep_renewal_by_a_brainpool_certificate(app, client, protocol_config, bp384_root, root_cert, tmp_path):
    from services.ca_service import CAService
    from tests.test_wstep_renew import RENEW_URL
    from tests.test_wstep_issue import _issued_cert_from_rstr
    key, csr = _bp_csr('wstep-renew-bp.example.test', 'EC-BP256')
    with app.app_context():
        cert_pem, _ = CAService.sign_csr_from_crypto(
            ca=db.session.get(CA, bp384_root['id']), csr=csr, validity_days=30, source='test')
    old = x509.load_pem_x509_certificate(cert_pem.encode() if isinstance(cert_pem, str) else cert_pem)
    new_csr = x509.CertificateSigningRequestBuilder().subject_name(old.subject).sign(key, hashes.SHA256())
    resp = client.post(RENEW_URL, data=_signed_renewal_rst(old, key, new_csr))
    assert resp.status_code == 200, resp.data
    renewed = _issued_cert_from_rstr(resp.data)
    assert renewed.serial_number != old.serial_number
    assert type(renewed.public_key().curve) is CURVES['EC-BP256']
    _check_chain(renewed, root_cert, tmp_path)


def test_scep_enrolls_a_brainpool_client_like_any_other_ec_curve(app, create_ca, tmp_path):
    from cryptography.hazmat.primitives.serialization import pkcs7
    from cryptography.x509.oid import AttributeOID
    from services.scep.scep_service import SCEPService
    from tests.test_scep_rfc8894_operations import (
        PKI_STATUS_OID, _build_request, _client_identity, _decrypt_password_response,
        _load_ca_material, _response_attributes)
    ca_data = create_ca(cn='SCEP Brainpool client CA')
    challenge = 'correct horse battery staple'
    key = ec.generate_private_key(ec.BrainpoolP384R1())
    client_cert, _ = _client_identity('Brainpool SCEP client', key=key)
    csr = x509.CertificateSigningRequestBuilder().subject_name(client_cert.subject).add_attribute(
        AttributeOID.CHALLENGE_PASSWORD, challenge.encode()).sign(key, hashes.SHA384())
    with app.app_context():
        ca, ca_cert, _ = _load_ca_material(ca_data['id'])
        request = _build_request(ca_cert, client_cert, key, 19, csr.public_bytes(serialization.Encoding.DER),
                                 b'bp-scep-nonce-01')
        response, status = SCEPService(ca.refid, challenge_password=challenge, auto_approve=True
                                       ).process_pkcs_req(request, '127.0.0.1')
    plaintext, _, _ = _decrypt_password_response(response, challenge)
    assert status == 200 and _response_attributes(response)[PKI_STATUS_OID] == '0'
    issued = pkcs7.load_der_pkcs7_certificates(plaintext)
    assert len(issued) == 1 and _curve(issued[0]) == 'brainpoolP384r1'
    _check_chain_rsa_ca = {'leaf.pem': _pem(issued[0]), 'ca.pem': _pem(ca_cert)}
    _openssl(tmp_path, 'verify', '-CAfile', 'ca.pem', 'leaf.pem', **_check_chain_rsa_ca)


# ---------------------------------------------------------------------------
# ACME client
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('label', ['EC-BP256', 'EC-BP384'])
def test_acme_client_csr_is_accepted_by_the_acme_server(app, monkeypatch, bp384_root, root_cert, label, tmp_path):
    """The client's own CSR for a Brainpool order, finalized by UCM's ACME server."""
    from models.acme_models import AcmeClientOrder
    from services.acme.acme_service import AcmeService
    from tests.test_acme_client_key_type import _finalize
    from tests.test_acme_profile_template import TestFinalizeWithBoundTemplate
    from utils import caa_checker
    with app.app_context():
        client_order = AcmeClientOrder(
            domains=json.dumps(['web.example.com']), challenge_type='http-01', environment='staging',
            status='ready', key_source='generate', key_type=label,
            order_url='https://ca.example/order/bp', finalize_url='https://ca.example/order/bp/finalize')
        (ok, msg, _), client_csr = _finalize(client_order)
        assert ok, msg
        assert type(client_csr.public_key().curve) is CURVES[label]
        assert type(client_csr.signature_hash_algorithm) is DIGESTS[label]
        refid = db.session.get(CA, bp384_root['id']).refid
        order = TestFinalizeWithBoundTemplate._order(None)
        service = AcmeService(base_url='http://localhost')
        monkeypatch.setattr(caa_checker, 'check_caa_for_domains', lambda *a, **k: (True, 'allowed'))
        monkeypatch.setattr(service, '_resolve_ca_for_domains', lambda _d: refid)
        service.begin_order_processing(order)
        service._finalizing_order_id = order.order_id
        ok, error = service.finalize_order(order.order_id, _pem(client_csr).decode())
        service._finalizing_order_id = None
        assert ok, error
        db.session.refresh(order)
        leaf = _row_cert(db.session.get(Certificate, order.certificate_id))
    _check_chain(leaf, root_cert, tmp_path)


def test_acme_client_key_types_offer_brainpool_for_certificates_only(auth_client):
    from services.acme.acme_client_service import ACCOUNT_KEY_TYPES, CERT_KEY_TYPES
    assert {'EC-BP256', 'EC-BP384'} <= set(CERT_KEY_TYPES)
    assert not any('BP' in k for k in ACCOUNT_KEY_TYPES)
    # An ACME account key has no Brainpool JWS algorithm
    r = _post(auth_client, '/api/v2/acme/accounts', {'email': 'bp-account@example.test',
                                                       'key_type': 'EC-BP256', 'agree_tos': True})
    assert r.status_code == 400 and 'Key type must be one of' in r.get_json()['message']
    assert 'EC-BP256' not in r.get_json()['message']


def test_acme_client_setting_takes_brainpool(app, auth_client):
    from models import SystemConfig
    r = auth_client.patch('/api/v2/acme/client/settings', content_type='application/json',
                          data=json.dumps({'key_type': 'EC-BP384'}))
    try:
        assert r.status_code == 200, r.get_json()
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key='acme.client.key_type').delete()
            db.session.commit()


# ---------------------------------------------------------------------------
# XCEP: Brainpool is not announced
# ---------------------------------------------------------------------------

def test_xcep_leaves_brainpool_templates_out():
    from tests.test_xcep_fips_request_hash import _build, _policies, _template, NS
    templates = [_template(1), _template(2, key_type='EC-P384')] + [
        _template(10 + i, key_type=label) for i, label in enumerate(CURVES)]
    root, _ = _build(templates)
    names = {p.findtext('.//x:commonName', namespaces=NS) for p in _policies(root)}
    assert names == {'T1', 'T2'}


@pytest.mark.parametrize('label', list(CURVES))
def test_xcep_key_type_info_is_none_for_brainpool(label):
    from services.xcep import policy_builder
    assert policy_builder._key_type_info(label) is None
    assert policy_builder._key_type_info('EC-P256') == ('ECDSA_P256', 256)


# ---------------------------------------------------------------------------
# FIPS mode: every gate refuses Brainpool
# ---------------------------------------------------------------------------

@pytest.fixture
def fips_on(monkeypatch):
    import fips_mode
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)


def test_fips_refuses_ca_creation(auth_client, fips_on):
    r = _post(auth_client, '/api/v2/cas', {'type': 'root', 'commonName': 'FIPS BP CA', 'keyAlgo': 'EC-BP384',
                                           'keySize': None, 'validityYears': 1})
    assert r.status_code == 400 and 'FIPS' in json.dumps(r.get_json())


def test_fips_refuses_form_leaf(auth_client, bp384_root, fips_on):
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': 'fips-bp.example.test', 'ca_id': bp384_root['id'], 'key_type': 'ec', 'curve': 'EC-BP256',
        'validity_days': 30})
    assert r.status_code == 400 and 'FIPS' in json.dumps(r.get_json())


def test_fips_refuses_a_brainpool_csr_on_every_protocol_gate(app, client, protocol_config, bp384_root, fips_on):
    from tests.test_wstep_issue import ISSUE_URL
    _, csr = _bp_csr('fips-gate.example.test')
    est = client.post('/.well-known/est/simpleenroll', data=base64.b64encode(csr.public_bytes(
        serialization.Encoding.DER)), headers=_basic(), content_type='application/pkcs10')
    assert est.status_code == 400 and b'FIPS' in est.data
    wstep = client.post(ISSUE_URL, data=_rst(csr), headers={
        'Authorization': 'Basic ' + base64.b64encode(b'bp-user:bp-password').decode()})
    assert wstep.status_code == 400 and b'FIPS' in wstep.data
    from utils.key_type import validate_enrollment_public_key
    assert 'FIPS' in validate_enrollment_public_key(csr.public_key())


def test_fips_refuses_acme_finalize_and_sign_csr(app, monkeypatch, auth_client, bp384_root, fips_on):
    from services.acme.acme_service import AcmeService
    from tests.test_acme_profile_template import TestFinalizeWithBoundTemplate
    from utils import caa_checker
    _, csr = _bp_csr('web.example.com')
    with app.app_context():
        refid = db.session.get(CA, bp384_root['id']).refid
        order = TestFinalizeWithBoundTemplate._order(None)
        service = AcmeService(base_url='http://localhost')
        monkeypatch.setattr(caa_checker, 'check_caa_for_domains', lambda *a, **k: (True, 'allowed'))
        monkeypatch.setattr(service, '_resolve_ca_for_domains', lambda _d: refid)
        service.begin_order_processing(order)
        service._finalizing_order_id = order.order_id
        ok, error = service.finalize_order(order.order_id, _pem(csr).decode())
        service._finalizing_order_id = None
    assert not ok and 'FIPS' in str(error)
    r = _post(auth_client, '/api/v2/csrs/upload', {'pem': _pem(csr).decode(), 'name': 'fips-bp'})
    if r.status_code in (200, 201):
        r = _post(auth_client, f'/api/v2/csrs/{r.get_json()["data"]["id"]}/sign',
                  {'ca_id': bp384_root['id'], 'validity_days': 30})
    assert r.status_code == 400 and 'FIPS' in json.dumps(r.get_json())


def test_fips_refuses_tsa_signer_and_acme_client_keys(app, auth_client, bp384_root, fips_on):
    from fips_mode import FipsRestricted
    from services import tsa_signer_cert
    from services.acme.acme_client_service import AcmeClientService
    with app.app_context(), pytest.raises((FipsRestricted, tsa_signer_cert.TsaSignerIssueError), match='FIPS'):
        tsa_signer_cert.issue_tsa_signer_certificate(
            ca=db.session.get(CA, bp384_root['id']), cn='fips-tsa.example.test', key_type='ec', curve='EC-BP256')
    key, error = AcmeClientService._generate_cert_key(
        object.__new__(AcmeClientService), type('Order', (), {'key_type': 'EC-BP256'})())
    assert key is None and 'FIPS' in error
    for url, body in (('/api/v2/acme/client/settings', {'key_type': 'EC-BP256'}),):
        r = auth_client.patch(url, content_type='application/json', data=json.dumps(body))
        assert r.status_code == 400 and 'FIPS' in r.get_json()['message']
    r = _post(auth_client, '/api/v2/acme/client/request', {
        'domains': ['fips.example.com'], 'email': 'a@example.com', 'challenge_type': 'http-01',
        'environment': 'staging', 'key_type': 'EC-BP384'})
    assert r.status_code == 400 and 'FIPS' in r.get_json()['message']
