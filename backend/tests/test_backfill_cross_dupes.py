"""The hourly SKI dedup merges only records holding the same certificate.

A cross-certificate shares the subject and key (hence the SKI) of the root it
cross-signs. Merging the two kept the cross-certified row, copied the root's key
into it and deleted the self-signed root (#400).
"""
import base64
import uuid
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import db, CA
from services.ski_aki_backfill import backfill_ski_aki
from utils.key_codec import store_pem_bytes


def _cert(subject_key, cn, issuer_key=None, issuer_cn=None):
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn or cn)])
    return (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
            .public_key(subject_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(subject_key.public_key()), critical=False)
            .sign(issuer_key or subject_key, hashes.SHA256()))


def _row(cert, key=None, caref=None, crt=None):
    ski = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.key_identifier
    pem_key = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()) if key else None
    row = CA(refid=str(uuid.uuid4()), descr=cert.subject.rfc4514_string(), serial=0,
             crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode() if crt is None else crt,
             prv=store_pem_bytes(pem_key) if pem_key else None, caref=caref,
             subject=cert.subject.rfc4514_string(), issuer=cert.issuer.rfc4514_string(),
             serial_number=str(cert.serial_number), ski=ski.hex(':').upper())
    db.session.add(row)
    db.session.commit()
    return row.id


def test_self_signed_root_survives_its_cross_certificate(app):
    key_a, key_b = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    with app.app_context():
        root_a = db.session.get(CA, _row(_cert(key_a, 'Cross Root A'), key_a))
        self_signed = _cert(key_b, 'Cross Root B')
        b_id = _row(self_signed, key_b)
        cross_id = _row(_cert(key_b, 'Cross Root B', key_a, 'Cross Root A'), caref=root_a.refid)
        b_crt = db.session.get(CA, b_id).crt

        stats = backfill_ski_aki()

        db.session.expire_all()
        b = db.session.get(CA, b_id)
        assert b is not None, 'self-signed root deleted'
        assert b.crt == b_crt and b.caref is None and b.prv
        assert db.session.get(CA, cross_id) is not None
        assert stats['same_key_distinct_certs'] >= 1


def test_identical_duplicates_are_still_merged(app):
    key = ec.generate_private_key(ec.SECP256R1())
    cert = _cert(key, 'Duplicate Root')
    with app.app_context():
        first = _row(cert, key)
        second = _row(cert)

        stats = backfill_ski_aki()

        db.session.expire_all()
        remaining = [i for i in (first, second) if db.session.get(CA, i) is not None]
        assert len(remaining) == 1
        assert db.session.get(CA, remaining[0]).prv
        assert stats['deduplicated'] >= 1


def test_pending_record_merges_into_its_certificate(app):
    """A pending CA (crt='') and the imported certificate for its key are one CA."""
    key_a, key_b = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    with app.app_context():
        root_a = db.session.get(CA, _row(_cert(key_a, 'Pending Parent'), key_a))
        signed = _cert(key_b, 'Pending Sub', key_a, 'Pending Parent')
        pending = _row(signed, key_b, crt='')
        imported = _row(signed, caref=root_a.refid)

        backfill_ski_aki()

        db.session.expire_all()
        remaining = [db.session.get(CA, i) for i in (pending, imported)]
        remaining = [r for r in remaining if r is not None]
        assert len(remaining) == 1
        assert remaining[0].prv and remaining[0].caref == root_a.refid
