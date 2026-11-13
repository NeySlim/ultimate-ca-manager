"""relink_parent_caref: between two records of the issuer's key, the self-signed root is the parent."""
import base64
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import NameOID

from models import CA, db
from services.import_service import relink_parent_caref
from services.ski_aki_backfill import backfill_ski_aki
from tests.fixtures.cross_pki import build_cross_pki, make_cert, new_key, pem


def _row(cert, descr, caref=None):
    ski = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.key_identifier
    row = CA(refid=str(uuid.uuid4()), descr=descr, serial=0, caref=caref,
             crt=base64.b64encode(pem(cert).encode()).decode(),
             subject=cert.subject.rfc4514_string(), issuer=cert.issuer.rfc4514_string(),
             serial_number=str(cert.serial_number), ski=ski.hex(':').upper())
    db.session.add(row)
    db.session.commit()
    return row


def _child_without_aki(name, issuer_cn, issuer_key):
    key = new_key()
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)]))
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(issuer_key, hashes.SHA256()))


@pytest.fixture
def rows(app):
    made = []
    yield made
    with app.app_context():
        for row_id in made:
            row = db.session.get(CA, row_id)
            if row is not None:
                db.session.delete(row)
        db.session.commit()


def _store(rows, *pairs):
    stored = [_row(cert, descr) for cert, descr in pairs]
    rows.extend(r.id for r in stored)
    return stored


@pytest.mark.parametrize('cross_first', [True, False])
def test_by_issuer_name_the_root_is_preferred_to_its_cross_certificate(app, rows, cross_first):
    pki = build_cross_pki()
    order = [(pki.cross_b, 'cross'), (pki.root_b, 'root')]
    order = order if cross_first else order[::-1]
    with app.app_context():
        stored = {descr: row for (_, descr), row in zip(order, _store(rows, *order))}
        child = _child_without_aki(f'No AKI child {pki.tag}', pki.name_b, pki.key_b)
        assert relink_parent_caref(child, None) == stored['root'].refid


@pytest.mark.parametrize('link_first', [True, False])
def test_by_aki_the_root_is_preferred_to_a_self_issued_link_certificate(app, rows, link_first):
    # A rollover link certificate: the root's name and key, signed by the old key
    pki = build_cross_pki()
    link = make_cert(pki.name_b, pki.key_b, pki.name_b, new_key())
    order = [(link, 'link'), (pki.root_b, 'root')] if link_first else [(pki.root_b, 'root'), (link, 'link')]
    with app.app_context():
        stored = {descr: row for (_, descr), row in zip(order, _store(rows, *order))}
        assert relink_parent_caref(pki.int_b, None) == stored['root'].refid


def test_the_hourly_repair_chains_an_orphan_under_the_root_and_leaves_a_linked_ca_alone(app, rows):
    pki = build_cross_pki()
    link = make_cert(pki.name_b, pki.key_b, pki.name_b, new_key())
    with app.app_context():
        link_row, root_row = _store(rows, (link, 'link'), (pki.root_b, 'root'))
        orphan, kept = _store(rows, (pki.int_b, 'orphan'),
                              (make_cert(f'Kept {pki.tag}', new_key(), pki.name_b, pki.key_b), 'kept'))
        kept.caref = link_row.refid
        db.session.commit()
        backfill_ski_aki()
        assert db.session.get(CA, orphan.id).caref == root_row.refid
        assert db.session.get(CA, kept.id).caref == link_row.refid
