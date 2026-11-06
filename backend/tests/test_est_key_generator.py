"""The EST key generator certificate that signs encrypted serverkeygen packages: made on first
use, reused, replaced near expiry or when the CA certificate changes, one row per CA."""
import base64
import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from asn1crypto import cms
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, padding as asym_padding, rsa
from cryptography.x509.oid import NameOID

from models import CA, Certificate, SystemConfig, db
from models.est_signer_cert import EstSignerCert
from services import est_key_generator
from tests.test_acme_pq import needs_openssl_35
from tests.test_est_rfc7030 import (
    EST_PASSWORD, EST_USER, _basic_auth, _make_csr, _multipart_parts, _post_csr, _set_config,
)
from tests.test_est_serverkeygen_cms import (
    ASYMMETRIC_ID, _decrypt_signed_data, _enrol_transport, _ski, needs_openssl,
    openssl_verify_signed_by,
)
from utils import key_algorithms
from utils.datetime_utils import utc_now

_KEYS = ('est_enabled', 'est_ca_refid', 'est_username', 'est_password', 'est_validity_days')


@pytest.fixture(scope='module')
def cas(create_ca):
    return {'lazy': create_ca(cn='EST generator lazy root'),
            'main': create_ca(cn='EST generator main root')}


@pytest.fixture
def use(app, cas):
    with app.app_context():
        previous = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None)
                    for k in _KEYS}

    def _use(which):
        with app.app_context():
            ca = db.session.get(CA, cas[which]['id'])
            for key, value in (('est_enabled', 'true'), ('est_ca_refid', ca.refid),
                               ('est_username', EST_USER), ('est_password', EST_PASSWORD),
                               ('est_validity_days', '30')):
                _set_config(key, value)
            return ca.id, x509.load_pem_x509_certificate(base64.b64decode(ca.crt))

    yield _use
    with app.app_context():
        for key, value in previous.items():
            row = SystemConfig.query.filter_by(key=key).first()
            if value is None:
                if row is not None:
                    db.session.delete(row)
            elif row is None:
                db.session.add(SystemConfig(key=key, value=value))
            else:
                row.value = value
        db.session.commit()


def _signer_serial(client, cn):
    """Serial of the certificate that signed an encrypted serverkeygen answer."""
    transport, client_key, client_pem = _enrol_transport(client, f'transport-{cn}')
    csr, _ = _make_csr(common_name=cn, extra_attributes=((ASYMMETRIC_ID, _ski(transport)),))
    r = _post_csr(client, 'serverkeygen', csr, client_cert_pem=client_pem)
    assert r.status_code == 200, r.data
    signed = cms.SignedData.load(_decrypt_signed_data(_multipart_parts(r)[1], client_key))
    return signed['signer_infos'][0]['sid'].chosen['serial_number'].native


def _row(app, ca_id):
    with app.app_context():
        return EstSignerCert.query.filter_by(ca_id=ca_id).all()


class TestLifecycle:

    def test_made_on_the_first_encrypted_request_only(self, app, client, use):
        ca_id, ca_cert = use('lazy')
        assert _row(app, ca_id) == []
        csr, _ = _make_csr(common_name='clear.generator.test')
        assert _post_csr(client, 'serverkeygen', csr, headers=_basic_auth()).status_code == 200
        assert _row(app, ca_id) == []
        serial = _signer_serial(client, 'first.generator.test')
        (row,) = _row(app, ca_id)
        delegate = x509.load_pem_x509_certificate(row.crt.encode())
        assert delegate.serial_number == serial
        delegate.verify_directly_issued_by(ca_cert)
        assert delegate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'EST key generator'
        assert row.prv.startswith('ENC:') or not row.prv.startswith('-----')

    def test_reused_across_requests(self, app, client, use):
        ca_id, _ = use('main')
        first = _signer_serial(client, 'reuse-1.generator.test')
        assert _signer_serial(client, 'reuse-2.generator.test') == first
        assert len(_row(app, ca_id)) == 1

    def test_reissued_when_less_than_30_days_remain(self, app, client, use):
        ca_id, _ = use('main')
        first = _signer_serial(client, 'near-1.generator.test')
        with app.app_context():
            row = EstSignerCert.query.filter_by(ca_id=ca_id).one()
            row.not_after = utc_now() + datetime.timedelta(days=10)
            db.session.commit()
        second = _signer_serial(client, 'near-2.generator.test')
        assert second != first
        (row,) = _row(app, ca_id)
        assert row.not_after - utc_now() > datetime.timedelta(days=300)

    def test_reissued_when_the_ca_certificate_changed(self, app, client, use):
        ca_id, _ = use('main')
        first = _signer_serial(client, 'ca-1.generator.test')
        with app.app_context():
            row = EstSignerCert.query.filter_by(ca_id=ca_id).one()
            real = row.issuer_fingerprint
            row.issuer_fingerprint = '0' * 64
            db.session.commit()
        assert _signer_serial(client, 'ca-2.generator.test') != first
        (row,) = _row(app, ca_id)
        assert row.issuer_fingerprint == real

    def test_neither_a_certificate_row_nor_a_ca_serial(self, app, client, use):
        ca_id, _ = use('main')
        with app.app_context():
            EstSignerCert.query.filter_by(ca_id=ca_id).delete()
            db.session.commit()
            before = db.session.get(CA, ca_id).serial
        _signer_serial(client, 'uncounted.generator.test')
        with app.app_context():
            # The transport and the generated key's certificate count; the delegate neither
            # counts nor shows in the inventory
            assert db.session.get(CA, ca_id).serial == (before or 0) + 2
            assert Certificate.query.filter(Certificate.subject_cn == 'EST key generator').count() == 0

    def test_the_delegate_key_follows_master_key_rotation(self, app, client, use):
        """encrypt-all-keys and the key removal walk MASTER_KEY_COLUMNS: the delegate key is one."""
        from security.encryption import master_key_values
        ca_id, _ = use('main')
        _signer_serial(client, 'rotation.generator.test')
        with app.app_context():
            (row,) = EstSignerCert.query.filter_by(ca_id=ca_id).all()
            found = [(attribute, fmt) for _label, value_row, attribute, fmt in master_key_values()
                     if isinstance(value_row, EstSignerCert) and value_row.id == row.id]
        assert found == [('prv', 'b64')]

    def test_a_failed_issuance_answers_5xx_and_issues_nothing(self, app, client, use):
        ca_id, _ = use('main')
        with app.app_context():
            EstSignerCert.query.filter_by(ca_id=ca_id).delete()
            db.session.commit()
        transport, _, client_pem = _enrol_transport(client, 'transport-fail.generator.test')
        cn = 'fail.generator.test'
        csr, _ = _make_csr(common_name=cn, extra_attributes=((ASYMMETRIC_ID, _ski(transport)),))
        with patch.object(est_key_generator, '_issue', side_effect=ValueError('CA key unavailable')):
            r = _post_csr(client, 'serverkeygen', csr, client_cert_pem=client_pem)
        assert r.status_code >= 500, r.data
        with app.app_context():
            assert Certificate.query.filter(Certificate.subject_cn == cn).count() == 0
        assert _row(app, ca_id) == []

    def test_two_first_requests_at_once_keep_one_row(self, app, use):
        ca_id, ca_cert = use('main')
        original = est_key_generator._issue
        competitor = {}

        def racing_issue(ca, issuer, key):
            # Another worker inserts and commits its delegate between our read and our insert
            other_key = key_algorithms.generate('RSA-3072')
            other_cert, not_after = original(ca, issuer, other_key)
            from utils.key_codec import store_pem_bytes
            from sqlalchemy import insert
            with db.engine.begin() as conn:
                conn.execute(insert(EstSignerCert.__table__).values(
                    ca_id=ca.id, crt=other_cert.public_bytes(serialization.Encoding.PEM).decode(),
                    prv=store_pem_bytes(other_key.private_bytes(
                        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption())),
                    issuer_fingerprint=est_key_generator._fingerprint(issuer),
                    not_after=not_after, created_at=utc_now()))
            competitor['cert'] = other_cert
            return original(ca, issuer, key)

        with app.app_context():
            EstSignerCert.query.filter_by(ca_id=ca_id).delete()
            db.session.commit()
            ca = db.session.get(CA, ca_id)
            with patch.object(est_key_generator, '_issue', side_effect=racing_issue):
                _key, cert = est_key_generator.key_generator(ca, ca_cert)
            assert cert == competitor['cert']
            assert EstSignerCert.query.filter_by(ca_id=ca_id).count() == 1


def _ca_like(key, *, hsm_key_id=None):
    from utils.key_codec import store_pem_bytes
    name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Generator Org'),
                      x509.NameAttribute(NameOID.COMMON_NAME, 'Generator test CA')])
    now = datetime.datetime.now(datetime.timezone.utc)
    digest = hashes.SHA256() if key_algorithms.needs_digest(key) else None
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False),
                           critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, digest))
    prv = None if hsm_key_id else store_pem_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    ca = SimpleNamespace(id=0, refid='generator-test', descr='Generator test CA', offline=False,
                         offline_reason=None, is_pending=False, hsm_key_id=hsm_key_id, prv=prv,
                         signature_scheme=None, revoked_in_chain=False)
    return ca, cert


def _ca_keys():
    keys = {
        'RSA-2048': (lambda: rsa.generate_private_key(65537, 2048), 'RSA-3072'),
        'EC-P384': (lambda: ec.generate_private_key(ec.SECP384R1()), 'EC-P384'),
        'EC-BP256': (lambda: ec.generate_private_key(ec.BrainpoolP256R1()), 'EC-BP256'),
        'ED25519': (ed25519.Ed25519PrivateKey.generate, 'ED25519'),
        'ED448': (ed448.Ed448PrivateKey.generate, 'ED25519'),
    }
    if key_algorithms.mldsa_supported():
        keys['ML-DSA-65'] = (lambda: key_algorithms.generate('ML-DSA-65'), 'ML-DSA-65')
    return keys


@needs_openssl
@pytest.mark.parametrize('ca_label', [
    pytest.param(name, marks=needs_openssl_35) if name.startswith('ML-DSA') else name
    for name in sorted(_ca_keys())])
def test_each_ca_family_issues_a_delegate_openssl_chains_to_the_ca(app, ca_label, tmp_path):
    from utils.est_cms import signed_key_package
    make, expected_label = _ca_keys()[ca_label]
    ca, ca_cert = _ca_like(make())
    with app.app_context():
        label = est_key_generator.delegate_key_label(ca_cert.public_key())
        assert label == expected_label
        delegate_key = key_algorithms.generate(label)
        delegate, _ = est_key_generator._issue(ca, ca_cert, delegate_key)
    usage = delegate.extensions.get_extension_for_class(x509.KeyUsage)
    assert usage.critical and usage.value.digital_signature and not usage.value.key_cert_sign
    signed = signed_key_package(ec.generate_private_key(ec.SECP256R1()), delegate_key, delegate,
                                (ca_cert,))
    (tmp_path / 'signed.p7').write_bytes(
        cms.ContentInfo({'content_type': 'signed_data', 'content': signed}).dump())
    (tmp_path / 'anchor.pem').write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    openssl_verify_signed_by(tmp_path / 'signed.p7', tmp_path / 'anchor.pem', delegate, tmp_path)


@pytest.mark.parametrize('ca_label, expected', [
    ('RSA-2048', 'RSA-3072'), ('EC-P384', 'EC-P384'), ('EC-BP256', 'EC-P256'),
    ('ED25519', 'EC-P256'), ('ED448', 'EC-P384'), ('ML-DSA-65', 'EC-P384')])
def test_fips_mode_keeps_the_delegate_on_approved_keys(monkeypatch, ca_label, expected):
    import fips_mode
    if ca_label not in _ca_keys():
        pytest.skip('this build has no ML-DSA')
    key = _ca_keys()[ca_label][0]()
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    assert est_key_generator.delegate_key_label(key.public_key()) == expected


def test_an_hsm_backed_ca_signs_the_delegate_through_its_provider(app):
    from services.hsm.hsm_private_key import HsmRSAPrivateKey
    real = rsa.generate_private_key(65537, 2048)
    ca, ca_cert = _ca_like(real, hsm_key_id=77)
    calls = []

    def provider_sign(key_id, data, algorithm=None, hash_algorithm=None, padding=None):
        calls.append((key_id, hash_algorithm))
        return real.sign(data, asym_padding.PKCS1v15(), getattr(hashes, hash_algorithm.upper())())

    with app.app_context(), \
            patch('services.hsm.ca_key_loader.load_hsm_private_key',
                  return_value=HsmRSAPrivateKey(77, real.public_key(), 'RSA-2048')), \
            patch('services.hsm.HsmService.signing_hash', side_effect=lambda k, a, r='sha256': r), \
            patch('services.hsm.HsmService.sign', side_effect=provider_sign):
        delegate, _ = est_key_generator._issue(ca, ca_cert, key_algorithms.generate('RSA-3072'))
    assert calls and calls[0][0] == 77
    delegate.verify_directly_issued_by(ca_cert)


def test_an_offline_ca_issues_no_delegate(app):
    ca, ca_cert = _ca_like(rsa.generate_private_key(65537, 2048))
    ca.offline = True
    from services.ca.ca_signing import CAOfflineError
    with app.app_context(), pytest.raises(CAOfflineError):
        est_key_generator._issue(ca, ca_cert, key_algorithms.generate('RSA-3072'))


def test_deleting_the_ca_deletes_its_key_generator(app, auth_client, create_ca):
    ca_data = create_ca(cn='EST generator deleted root')
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        est_key_generator.key_generator(ca, x509.load_pem_x509_certificate(base64.b64decode(ca.crt)))
        assert EstSignerCert.query.filter_by(ca_id=ca.id).count() == 1
    assert auth_client.delete(f"/api/v2/cas/{ca_data['id']}").status_code in (200, 204)
    with app.app_context():
        assert EstSignerCert.query.filter_by(ca_id=ca_data['id']).count() == 0
