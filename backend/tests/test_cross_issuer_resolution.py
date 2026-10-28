"""OCSP, mTLS enrolment and renewal name the self-signed record, not a stored cross-certificate (#400)."""
import base64
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from models import CA, Certificate, db
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import build_cross_pki, make_cert, new_key, pem


@pytest.fixture
def pki():
    return build_cross_pki()


@pytest.fixture
def stored(app, pki):
    """The cross-certificate record (lower id), then Root B."""
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a) + pem(pki.cross_b))
        SmartImporter().execute(pem(pki.root_b))
        rows = CA.query.filter(CA.descr == pki.name_b).order_by(CA.id).all()
        assert len(rows) == 2
        cross = next(r for r in rows if r.issuer != r.subject)
        root = next(r for r in rows if r.issuer == r.subject)
        assert cross.id < root.id
        yield root.refid, cross.refid


def _leaf_under_b(pki):
    return make_cert(f'l-{uuid.uuid4().hex[:6]}.example', new_key(), pki.name_b, pki.key_b, ca=False,
                     san='l.example')


def test_ocsp_issuer_hash_resolves_to_the_root(app, pki, stored):
    from api.ocsp_routes import _find_ca_by_issuer_hash
    root, _ = stored
    digest = hashes.Hash(hashes.SHA1())
    digest.update(pki.root_b.subject.public_bytes(serialization.Encoding.DER))
    name_hash = digest.finalize()
    digest = hashes.Hash(hashes.SHA1())
    digest.update(pki.root_b.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    key_hash = digest.finalize()
    with app.app_context():
        assert _find_ca_by_issuer_hash(name_hash, key_hash, hashes.SHA1()).refid == root


def test_mtls_enrolment_issuer_is_the_root(app, pki, stored):
    from services.mtls_enrollment import issuing_ca_for
    root, _ = stored
    with app.app_context():
        assert issuing_ca_for(_leaf_under_b(pki)).refid == root


def test_renewal_issuer_of_an_unlinked_certificate_is_the_root(app, pki, stored):
    from services.cert.renewal import resolve_issuing_ca
    root, _ = stored
    leaf = _leaf_under_b(pki)
    with app.app_context():
        row = Certificate(refid=str(uuid.uuid4()), descr='unlinked', crt=base64.b64encode(pem(leaf).encode()).decode(),
                          subject=leaf.subject.rfc4514_string(), issuer=leaf.issuer.rfc4514_string(),
                          serial_number=str(leaf.serial_number))
        db.session.add(row)
        db.session.commit()
        assert resolve_issuing_ca(row).refid == root
