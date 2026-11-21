"""FIPS mode approves an RSA key by one rule (FIPS 186-5 §5.1, IG C.F, OpenSSL's cap):
an even modulus of 2048 to 16384 bits, at issuance, for HSM signing and in the preflight.
Outside FIPS mode nothing changes."""
import base64
import json
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import fips_mode
from models import Certificate, db
from services import fips_preflight
from services.policy_service import PolicyEvaluationService
from utils import key_algorithms

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

SIZES = [(1024, False), (2046, False), (2047, False), (2048, True), (2049, False), (2050, True),
         (3072, True), (8192, True), (8193, False), (16384, True), (16385, False), (16386, False)]


def _public(bits):
    # Any odd modulus of exactly *bits* bits: only its length is judged
    return rsa.RSAPublicNumbers(65537, (1 << (bits - 1)) | 1).public_key()


@pytest.fixture
def fips(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)


@pytest.mark.parametrize('bits, approved', SIZES)
def test_the_rule(bits, approved):
    assert key_algorithms.fips_rsa_bits_approved(bits) is approved


@pytest.mark.parametrize('bits, approved', SIZES)
def test_every_path_applies_it(app, fips, bits, approved):
    assert key_algorithms.fips_approved_for_key(_public(bits)) is approved
    assert fips_preflight.stored_label_approved(f'RSA {bits}') is approved
    assert fips_preflight.stored_label_approved(f'RSA-{bits}') is approved
    with app.app_context():
        violations, _, _ = PolicyEvaluationService.enforce_rules([], key_type=f'RSA-{bits}')
        assert (violations == []) is approved, violations
        by_key = PolicyEvaluationService.algorithm_violations(None, public_key=_public(bits))
        assert (by_key == []) is approved, by_key


@pytest.mark.parametrize('bits', [1024, 2049, 8192, 16386])
def test_outside_fips_nothing_changes(app, bits):
    with app.app_context():
        assert PolicyEvaluationService.enforce_rules([], key_type=f'RSA-{bits}')[0] == []
        assert PolicyEvaluationService.algorithm_violations(None, public_key=_public(bits)) == []


def test_forms_still_offer_the_registered_sizes(app, fips):
    """Only issuance widens: what UCM generates and proposes stays 2048, 3072 and 4096."""
    with app.app_context():
        key_types, _ = PolicyEvaluationService.effective_algorithms(None)
    assert [k for k in key_types if k.startswith('RSA-')] == ['RSA-2048', 'RSA-3072', 'RSA-4096']


def test_an_operator_policy_still_narrows(app, fips):
    from models.policy import CertificatePolicy
    with app.app_context():
        pol = CertificatePolicy(name=f'rsa2048-{uuid.uuid4().hex[:6]}', policy_type='issuance',
                                is_active=True, priority=100)
        pol.set_rules({'allowed_key_types': ['RSA-2048']})
        db.session.add(pol)
        db.session.commit()
        try:
            violations, _, _ = PolicyEvaluationService.enforce_rules([pol], key_type='RSA-8192')
            assert len(violations) == 1 and pol.name in violations[0], violations
        finally:
            db.session.delete(pol)
            db.session.commit()


@pytest.fixture(scope='module')
def rsa8192():
    return rsa.generate_private_key(public_exponent=65537, key_size=8192)


def test_an_rsa_8192_csr_is_signed_in_fips_mode(app, auth_client, create_ca, monkeypatch, rsa8192):
    ca = create_ca(cn='FIPS RSA-8192 CA')
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'big.fips.test')]))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName('big.fips.test')]), critical=False)
           .sign(rsa8192, hashes.SHA256()))
    with app.app_context():
        row = Certificate(refid=str(uuid.uuid4()), descr='fips-rsa8192-csr', source='manual',
                          csr=base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode())
        db.session.add(row)
        db.session.commit()
        csr_id = row.id
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    try:
        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', content_type='application/json',
                             data=json.dumps({'ca_id': ca['id']}))
        assert r.status_code in (200, 201), r.data
    finally:
        with app.app_context():
            row = db.session.get(Certificate, csr_id)
            if row is not None:
                db.session.delete(row)
                db.session.commit()


def _fake_private(bits):
    # Unchecked key of exactly *bits* bits: only its size is judged, no prime search
    p, q = (1 << (bits // 2 - 1)) + 1, (1 << (bits - bits // 2)) + 1
    numbers = rsa.RSAPrivateNumbers(p=p, q=q, d=3, dmp1=1, dmq1=1, iqmp=1,
                                    public_numbers=rsa.RSAPublicNumbers(65537, p * q))
    key = numbers.private_key(unsafe_skip_rsa_key_validation=True)
    assert key.key_size == bits
    return key


@pytest.mark.parametrize('bits, approved', [(2048, True), (2050, True), (8192, True), (16384, True),
                                            (2049, False), (16386, False)])
def test_a_policy_is_saved_by_the_rule(app, auth_client, fips, bits, approved):
    from models.policy import CertificatePolicy
    name = f'fips-rsa-{bits}-{uuid.uuid4().hex[:6]}'
    r = auth_client.post('/api/v2/policies', content_type='application/json', data=json.dumps({
        'name': name, 'is_active': False, 'rules': {'allowed_key_types': [f'RSA-{bits}']}}))
    with app.app_context():
        row = CertificatePolicy.query.filter_by(name=name).first()
        if row is not None:
            db.session.delete(row)
            db.session.commit()
    assert (r.status_code in (200, 201)) is approved, r.data
    assert (row is not None) is approved


@pytest.mark.parametrize('bits', [1024, 2049, 16386])
def test_a_reused_key_outside_the_rule_is_refused(fips, bits):
    from services.acme.acme_client_service import fips_private_key_refusal
    key = _fake_private(bits)
    refusal = fips_private_key_refusal(key)
    assert refusal and f'RSA {bits}' in refusal


@pytest.mark.parametrize('bits', [2048, 2050, 8192])
def test_a_reused_key_inside_the_rule_is_accepted(fips, bits):
    from services.acme.acme_client_service import fips_private_key_refusal
    assert fips_private_key_refusal(_fake_private(bits)) is None


def _pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


@pytest.mark.parametrize('bits', [1024, 2049, 16386])
def test_an_imported_account_key_outside_the_rule_is_refused(fips, monkeypatch, bits):
    from api.v2.acme_client.accounts import _validate_imported_account_key
    key = _fake_private(bits)
    monkeypatch.setattr(serialization, 'load_pem_private_key', lambda *a, **k: key)
    with pytest.raises(ValueError) as caught:
        _validate_imported_account_key(_pem(key))
    assert 'FIPS' in str(caught.value)


@pytest.mark.parametrize('bits', [2049, 2050])
def test_an_imported_account_key_outside_fips(monkeypatch, bits):
    from api.v2.acme_client.accounts import _validate_imported_account_key
    key = _fake_private(bits)
    monkeypatch.setattr(serialization, 'load_pem_private_key', lambda *a, **k: key)
    assert _validate_imported_account_key(_pem(key)) == 'RS256'


def test_the_refusal_states_the_rsa_rule(fips):
    """An RSA size outside the rule is refused with the rule, not a list of three sizes."""
    from services.policy_service import PolicyEvaluationService, fips_policy
    violations = PolicyEvaluationService.enforce_rules([fips_policy()], key_type='RSA-2049', notify=False)[0]
    assert len(violations) == 1, violations
    text = violations[0]
    assert 'RSA of an even length from 2048 to 16384 bits' in text, text
    assert 'RSA-2048' not in text and 'RSA-4096' not in text, text
    assert 'EC-P256' in text, text


def _certificate_for(public_key):
    from datetime import datetime, timedelta, timezone

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'est client')])
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(public_key)
            .serial_number(1).not_valid_before(now).not_valid_after(now + timedelta(days=1))
            .sign(ec.generate_private_key(ec.SECP256R1()), hashes.SHA256()))


@pytest.mark.parametrize('bits, in_fips, refused', [
    (2049, True, True), (16386, True, True), (2050, True, False), (8192, True, False),
    (2049, False, False), (1024, False, True)])
def test_est_key_transport_follows_the_rsa_rule(monkeypatch, bits, in_fips, refused):
    from utils.est_key_encryption import recipient_refusal
    monkeypatch.setattr(fips_mode, 'enabled', lambda: in_fips)
    refusal = recipient_refusal(_certificate_for(_fake_private(bits).public_key()))
    assert (refusal is not None) is refused, refusal
