"""Post-quantum test material, made once by OpenSSL 3.5 (``fixtures/pqc/regenerate.sh``)
and only read here: no test runs openssl."""
import base64
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

PQC_DIR = Path(__file__).parent / 'fixtures' / 'pqc'
P12_PASSWORD = b'pqc-fixture'   # as in regenerate.sh


def fixture_bytes(name: str) -> bytes:
    return (PQC_DIR / name).read_bytes()


def load_mldsa_key():
    """The fixture ML-DSA-65 private key (seed-only PKCS#8, the layout pyca reads)."""
    return serialization.load_pem_private_key(fixture_bytes('mldsa65-seed.pem'), None)


@pytest.fixture
def mldsa_key():
    return load_mldsa_key()


@pytest.fixture
def mldsa_csr():
    """CSR made by OpenSSL with ``mldsa_key``, subject CN=UCM PQC fixture ML-DSA-65."""
    return x509.load_pem_x509_csr(fixture_bytes('mldsa65-csr.pem'))


@pytest.fixture
def mldsa_ca(app):
    """CA row inserted directly with the self-signed ``mldsa65-cert.pem`` and ``mldsa_key``,
    since UCM cannot create an ML-DSA CA yet; runs inside an app context."""
    with mldsa_ca_row(app) as ca:
        yield ca


@contextmanager
def mldsa_ca_row(app):
    """Body of ``mldsa_ca``; its CRLs and certificates go with it."""
    from models import CA, db
    pem = fixture_bytes('mldsa65-cert.pem')
    cert = x509.load_pem_x509_certificate(pem)
    name = cert.subject.rfc4514_string()
    refid = f'pqc-mldsa65-{uuid.uuid4().hex[:12]}'
    with app.app_context():
        ca = CA(refid=refid, descr=f'PQC fixture {refid}', serial=0,
                crt=base64.b64encode(pem).decode(),
                prv=base64.b64encode(fixture_bytes('mldsa65-seed.pem')).decode(),
                subject=name, issuer=name, serial_number=str(cert.serial_number),
                ski=cert.extensions.get_extension_for_class(
                    x509.SubjectKeyIdentifier).value.key_identifier.hex(':').upper(),
                valid_from=cert.not_valid_before_utc, valid_to=cert.not_valid_after_utc,
                imported_from='manual')
        db.session.add(ca)
        db.session.commit()
        ca_id = ca.id
        try:
            yield ca
        finally:
            from models import Certificate, CRLMetadata
            db.session.rollback()
            # Children first: a reused id would inherit them, and PostgreSQL refuses the delete.
            CRLMetadata.query.filter_by(ca_id=ca_id).delete()
            Certificate.query.filter_by(caref=refid).delete()
            CA.query.filter_by(refid=refid).delete()
            db.session.commit()


def scep_wstep_mldsa_signed_cms(data, key, cert=None, attrs=(), digest='sha512',
                                sid='issuer_and_serial', with_certificate=True):
    """CMS SignedData signed the RFC 9882 way: messageDigest, pure ML-DSA over the DER
    SignedAttrs, the key's OID as signatureAlgorithm with no parameters. ``sid='ski'``
    names the signer by the SKI of *key*, as Windows "Full PKCS#7" requests do."""
    import asn1crypto.cms
    import asn1crypto.core
    import asn1crypto.x509
    from cryptography.hazmat.primitives import hashes
    from utils import key_algorithms

    h = hashes.Hash({'sha512': hashes.SHA512, 'sha256': hashes.SHA256}[digest]())
    h.update(data)
    signed_attrs = asn1crypto.cms.CMSAttributes([
        *attrs,
        {'type': 'content_type', 'values': ['data']},
        {'type': 'message_digest', 'values': [asn1crypto.core.OctetString(h.finalize())]},
    ])
    signature = key.sign(b'\x31' + signed_attrs.dump()[1:])
    cert_asn1 = (asn1crypto.x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))
                 if cert is not None else None)
    if sid == 'ski':
        signer_id = {'subject_key_identifier':
                     x509.SubjectKeyIdentifier.from_public_key(key.public_key()).digest}
    else:
        signer_id = {'issuer_and_serial_number': {'issuer': cert_asn1.issuer,
                                                  'serial_number': cert_asn1.serial_number}}
    oid = next(a.oid for a in key_algorithms.algorithms('ML-DSA') if a.matches_key(key))
    version = 'v3' if sid == 'ski' else 'v1'
    signer_info = asn1crypto.cms.SignerInfo({
        'version': version, 'sid': signer_id,
        'digest_algorithm': {'algorithm': digest}, 'signed_attrs': signed_attrs,
        'signature_algorithm': {'algorithm': oid},
        'signature': asn1crypto.core.OctetString(signature),
    })
    content = {
        'version': version, 'digest_algorithms': [{'algorithm': digest}],
        'encap_content_info': {'content_type': 'data', 'content': data},
        'signer_infos': [signer_info],
    }
    if with_certificate and cert_asn1 is not None:
        content['certificates'] = [cert_asn1]
    return asn1crypto.cms.ContentInfo({'content_type': 'signed_data', 'content': content}).dump()
