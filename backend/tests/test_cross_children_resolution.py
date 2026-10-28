"""Every path that names a CA's issuer by SKI picks the self-signed record when a cross-certificate shares it (#400)."""
import base64
import uuid

import pytest
from cryptography import x509

from models import CA, Certificate, db
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import build_cross_pki, key_pem, make_cert, new_key, pem
from utils.key_codec import store_pem_bytes


@pytest.fixture
def pki():
    return build_cross_pki()


@pytest.fixture
def stored(app, pki):
    """Root A, then its cross-certificate of B (lower id), then Root B."""
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a) + pem(pki.cross_b))
        SmartImporter().execute(pem(pki.root_b))
        rows = CA.query.filter(CA.descr == pki.name_b).order_by(CA.id).all()
        assert len(rows) == 2
        cross = next(r for r in rows if r.issuer != r.subject)
        root = next(r for r in rows if r.issuer == r.subject)
        assert cross.id < root.id
        yield root.refid, cross.refid


def _direct(pki, ca=True):
    key = new_key()
    name = f'Direct {uuid.uuid4().hex[:6]}'
    cert = make_cert(name, key, pki.name_b, pki.key_b, ca=ca, path_length=0 if ca else None,
                     san=None if ca else f'{name.lower().replace(" ", "")}.example')
    return name, key, cert


def test_classic_leaf_import_parents_under_the_root(app, auth_client, pki, stored):
    root, _ = stored
    name, _, cert = _direct(pki, ca=False)
    r = auth_client.post('/api/v2/certificates/import', data={'pem_content': pem(cert)},
                         content_type='multipart/form-data')
    assert r.status_code in (200, 201), r.data
    with app.app_context():
        assert Certificate.query.filter(Certificate.descr.contains(name)).one().caref == root


def test_external_ca_certificate_parents_under_the_root(app, pki, stored):
    from services.ca_service import CAService
    root, _ = stored
    name, key, cert = _direct(pki)
    with app.app_context():
        ca = CA(refid=str(uuid.uuid4()), descr=name, crt='', serial=0,
                prv=store_pem_bytes(key_pem(key).encode()),
                subject=cert.subject.rfc4514_string())
        db.session.add(ca)
        db.session.commit()
        CAService.complete_external_ca(ca, pem(cert).encode())
        assert CA.query.filter_by(descr=name).one().caref == root


def test_backfill_rechains_an_orphan_ca_and_an_orphan_certificate_to_the_root(app, pki, stored):
    from services.ski_aki_backfill import backfill_ski_aki
    root, _ = stored
    _, _, int_cert = _direct(pki)
    _, _, leaf_cert = _direct(pki, ca=False)
    ski = lambda c: c.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.key_identifier.hex(':').upper()
    with app.app_context():
        ca = CA(refid=str(uuid.uuid4()), descr='orphan int', serial=0, crt=base64.b64encode(pem(int_cert).encode()).decode(),
                subject=int_cert.subject.rfc4514_string(), issuer=int_cert.issuer.rfc4514_string(),
                serial_number=str(int_cert.serial_number), ski=ski(int_cert))
        cert = Certificate(refid=str(uuid.uuid4()), descr='orphan leaf', crt=base64.b64encode(pem(leaf_cert).encode()).decode(),
                           subject=leaf_cert.subject.rfc4514_string(), issuer=leaf_cert.issuer.rfc4514_string(),
                           serial_number=str(leaf_cert.serial_number),
                           aki=pki.root_b.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.key_identifier.hex(':').upper())
        db.session.add_all([ca, cert])
        db.session.commit()
        backfill_ski_aki()
        assert CA.query.filter_by(descr='orphan int').one().caref == root
        assert Certificate.query.filter_by(descr='orphan leaf').one().caref == root


def test_relink_parent_caref_prefers_the_root(app, pki, stored):
    from services.import_service import relink_parent_caref
    root, _ = stored
    _, _, cert = _direct(pki)
    with app.app_context():
        assert relink_parent_caref(cert, None) == root


def test_issuing_ca_of_an_unlinked_ca_is_the_root(app, pki, stored):
    root, _ = stored
    name, _, cert = _direct(pki)
    with app.app_context():
        ca = CA(refid=str(uuid.uuid4()), descr=name, serial=0, crt=base64.b64encode(pem(cert).encode()).decode(),
                subject=cert.subject.rfc4514_string(), issuer=cert.issuer.rfc4514_string(),
                serial_number=str(cert.serial_number))
        db.session.add(ca)
        db.session.commit()
        assert ca.issuing_ca().refid == root
