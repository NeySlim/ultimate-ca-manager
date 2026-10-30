"""ML-DSA signatures are verified wherever UCM checks who issued a certificate;
SLH-DSA stays readable but never verified, and an unverifiable key is no longer
taken for a root when its key identifiers say another key signed it."""
import base64
import datetime
import uuid
from contextlib import contextmanager

import asn1crypto.x509
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import mldsa, padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from tests.pqc_fixtures import fixture_bytes

NOW = datetime.datetime.now(datetime.timezone.utc)


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _cert(subject_key, cn, issuer_key=None, issuer_cn=None, ca=True, aki=True, eku=None):
    issuer_key = issuer_key or subject_key
    builder = (x509.CertificateBuilder().subject_name(_name(cn)).issuer_name(_name(issuer_cn or cn))
               .public_key(subject_key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(NOW - datetime.timedelta(minutes=5))
               .not_valid_after(NOW + datetime.timedelta(days=30))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(subject_key.public_key()),
                              critical=False))
    if aki:
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()), critical=False)
    if eku:
        builder = builder.add_extension(x509.ExtendedKeyUsage(eku), critical=False)
    digest = None if isinstance(issuer_key, (mldsa.MLDSA44PrivateKey, mldsa.MLDSA65PrivateKey)) \
        else hashes.SHA256()
    return builder.sign(issuer_key, digest)


@pytest.fixture(scope='module')
def chain():
    """ML-DSA-65 root -> ML-DSA-44 intermediate -> RSA leaf."""
    root_key, inter_key = mldsa.MLDSA65PrivateKey.generate(), mldsa.MLDSA44PrivateKey.generate()
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root = _cert(root_key, 'PQ root')
    inter = _cert(inter_key, 'PQ intermediate', root_key, 'PQ root')
    leaf = _cert(leaf_key, 'pq-leaf.test', inter_key, 'PQ intermediate', ca=False)
    return {'root': root, 'inter': inter, 'leaf': leaf,
            'root_key': root_key, 'inter_key': inter_key}


def _pem(*certs):
    return ''.join(c.public_bytes(serialization.Encoding.PEM).decode() for c in certs)


# ------------------------------------------------------ the issuer check

def test_each_link_verifies(chain):
    from utils.cert_issuer import certificate_signed_by
    assert certificate_signed_by(chain['inter'], chain['root']) is True
    assert certificate_signed_by(chain['leaf'], chain['inter']) is True
    assert certificate_signed_by(chain['leaf'], chain['root']) is False


def test_ml_dsa_root_is_self_signed(chain):
    from utils.cert_issuer import is_self_signed
    assert is_self_signed(chain['root']) is True


def test_self_issued_ml_dsa_certificate_signed_by_another_key_is_no_root(chain):
    from utils.cert_issuer import is_self_signed
    other = _cert(mldsa.MLDSA65PrivateKey.generate(), 'PQ root', chain['root_key'], 'PQ root')
    assert is_self_signed(other) is False


def test_slh_dsa_is_never_verified():
    from utils.cert_issuer import UnsupportedIssuerKey, certificate_signed_by, is_self_signed
    cert = x509.load_pem_x509_certificate(fixture_bytes('slhdsa-sha2-128s-cert.pem'))
    with pytest.raises(UnsupportedIssuerKey):
        certificate_signed_by(cert, cert)
    assert is_self_signed(cert) is True  # DN match, no key identifier against it


def _slh_dsa_key_signed_elsewhere():
    """The SLH-DSA fixture's key and DN, its AKI pointing at another key, signed with RSA."""
    parsed = asn1crypto.x509.Certificate.load(
        x509.load_pem_x509_certificate(fixture_bytes('slhdsa-sha2-128s-cert.pem'))
        .public_bytes(serialization.Encoding.DER))
    tbs = parsed['tbs_certificate'].copy()
    sig_alg = asn1crypto.x509.SignedDigestAlgorithm({'algorithm': 'sha256_rsa'})
    tbs['signature'] = sig_alg
    extensions = [e for e in tbs['extensions'] if e['extn_id'].native != 'authority_key_identifier']
    extensions.append({'extn_id': 'authority_key_identifier', 'critical': False,
                       'extn_value': {'key_identifier': b'\x01' * 20}})
    tbs['extensions'] = extensions
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signature = key.sign(tbs.dump(), padding.PKCS1v15(), hashes.SHA256())
    der = asn1crypto.x509.Certificate({'tbs_certificate': tbs, 'signature_algorithm': sig_alg,
                                       'signature_value': signature}).dump()
    return x509.load_der_x509_certificate(der)


def test_unverifiable_self_issued_certificate_with_foreign_aki_is_no_root():
    from utils.cert_issuer import is_self_signed
    cert = _slh_dsa_key_signed_elsewhere()
    assert cert.subject == cert.issuer
    assert is_self_signed(cert) is False


# --------------------------------------------------------- the callers

def test_smart_import_chain_is_verified(chain):
    from services.smart_import.chain_builder import ChainBuilder
    from services.smart_import.parser import SmartParser
    objs = SmartParser().parse(_pem(chain['leaf'], chain['inter'], chain['root']))
    chains = [c.to_dict() for c in ChainBuilder().build_chains(objs)]
    assert [c['chain_length'] for c in chains] == [3]
    assert chains[0]['verifiable'] is True and chains[0]['is_valid'] is True, chains[0]['errors']


def test_ocsp_delegated_responder_signed_by_ml_dsa(chain):
    from services.ocsp_service import OCSPService
    responder = _cert(rsa.generate_private_key(public_exponent=65537, key_size=2048), 'PQ OCSP',
                      chain['inter_key'], 'PQ intermediate', ca=False,
                      eku=[ExtendedKeyUsageOID.OCSP_SIGNING])
    OCSPService._verify_certificate_signature(responder, chain['inter'])
    with pytest.raises(Exception):
        OCSPService._verify_certificate_signature(responder, chain['root'])


@contextmanager
def _ca_rows(app, *certs):
    """CA rows holding *certs* (no key), in insertion order; removed afterwards."""
    from models import CA, db
    refids = []
    with app.app_context():
        rows = []
        for cert in certs:
            refid = f'pq-chain-{uuid.uuid4().hex[:10]}'
            refids.append(refid)
            rows.append(CA(refid=refid, descr=refid, serial=0,
                           crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
                           subject=cert.subject.rfc4514_string(), issuer=cert.issuer.rfc4514_string(),
                           serial_number=str(cert.serial_number), imported_from='manual'))
            db.session.add(rows[-1])
            db.session.commit()
        try:
            yield rows
        finally:
            db.session.rollback()
            CA.query.filter(CA.refid.in_(refids)).delete(synchronize_session=False)
            db.session.commit()


def test_intermediate_finds_its_real_ml_dsa_parent_not_a_decoy(app, chain):
    decoy = _cert(mldsa.MLDSA65PrivateKey.generate(), 'PQ root')
    # no AKI: the parent is found by DN, where the decoy comes first
    inter = _cert(chain['inter_key'], 'PQ intermediate', chain['root_key'], 'PQ root', aki=False)
    with _ca_rows(app, decoy, chain['root'], inter) as (decoy_row, root_row, inter_row):
        assert inter_row.issuing_ca().id == root_row.id


def test_mtls_enrolment_finds_its_ml_dsa_issuer(app, mldsa_key, mldsa_ca):
    from services.mtls_enrollment import issuing_ca_for
    ca_cert = x509.load_pem_x509_certificate(fixture_bytes('mldsa65-cert.pem'))
    user_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (x509.CertificateBuilder().subject_name(_name('pq-mtls-user'))
            .issuer_name(ca_cert.subject).public_key(user_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(NOW - datetime.timedelta(minutes=5))
            .not_valid_after(NOW + datetime.timedelta(days=30)).sign(mldsa_key, None))
    with app.app_context():
        found = issuing_ca_for(leaf)
        assert found is not None and found.refid == mldsa_ca.refid
