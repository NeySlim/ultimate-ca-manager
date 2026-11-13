"""Between two records of the issuer's key, the self-signed root is the parent: relink, SKI lookup, pending CA."""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import NameOID

from models import CA, db
from services.import_service import relink_parent_caref
from services.ski_aki_backfill import backfill_ski_aki
from tests.conftest import assert_success
from utils.cert_issuer import find_ca_by_ski, signing_ca_for
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


def _same_key_record(pki, kind):
    """A second record of Root B's key: its cross certificate or a self-issued link certificate."""
    return pki.cross_b if kind == 'cross' else make_cert(pki.name_b, pki.key_b, pki.name_b, new_key())


@pytest.mark.parametrize('kind', ['cross', 'link'])
@pytest.mark.parametrize('other_first', [True, False])
def test_the_lookup_by_ski_returns_the_root_before_another_record_of_its_key(app, rows, kind, other_first):
    pki = build_cross_pki()
    order = [(_same_key_record(pki, kind), 'other'), (pki.root_b, 'root')]
    order = order if other_first else order[::-1]
    with app.app_context():
        stored = {descr: row for (_, descr), row in zip(order, _store(rows, *order))}
        assert find_ca_by_ski(stored['root'].ski).id == stored['root'].id
        assert signing_ca_for(pki.int_b).id == stored['root'].id


def _sign_csr(csr_pem, issuer_cn, issuer_key, with_aki):
    csr = x509.load_pem_x509_csr(csr_pem.encode())
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(csr.subject)
               .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)]))
               .public_key(csr.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
               .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(csr.public_key()), critical=False))
    if with_aki:
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()), critical=False)
    return pem(builder.sign(issuer_key, hashes.SHA256()))


@pytest.mark.parametrize('kind', ['cross', 'link'])
@pytest.mark.parametrize('with_aki', [True, False])
@pytest.mark.parametrize('other_first', [True, False])
def test_a_pending_ca_is_chained_under_the_root_not_another_record_of_its_key(
        app, auth_client, rows, kind, with_aki, other_first):
    pki = build_cross_pki()
    order = [(_same_key_record(pki, kind), 'other'), (pki.root_b, 'root')]
    order = order if other_first else order[::-1]
    with app.app_context():
        stored = {descr: row for (_, descr), row in zip(order, _store(rows, *order))}
        root_refid = stored['root'].refid
    resp = auth_client.post('/api/v2/cas', data=json.dumps({
        'type': 'external', 'commonName': f'Pending under B {pki.tag}', 'keyAlgo': 'ECDSA',
        'keySize': 'secp256r1'}), content_type='application/json')
    pending = assert_success(resp, status=201)
    rows.append(pending['id'])
    signed = _sign_csr(pending['csr_pem'], pki.name_b, pki.key_b, with_aki)
    resp = auth_client.post(f"/api/v2/cas/{pending['id']}/certificate",
                            data=json.dumps({'pem_content': signed}), content_type='application/json')
    assert assert_success(resp)['caref'] == root_refid


@pytest.mark.parametrize('kind', ['cross', 'link'])
def test_a_ca_without_caref_or_aki_resolves_its_issuer_to_the_root(app, rows, kind):
    pki = build_cross_pki()
    child = _child_without_aki(f'No AKI issuing {pki.tag}', pki.name_b, pki.key_b)
    with app.app_context():
        _other, root, child_row = _store(rows, (_same_key_record(pki, kind), 'other'),
                                         (pki.root_b, 'root'), (child, 'child'))
        assert child_row.caref is None
        assert child_row.issuing_ca().id == root.id


@pytest.mark.parametrize('kind', ['cross', 'link'])
@pytest.mark.parametrize('with_aki', [True, False])
def test_an_export_completes_a_chain_with_the_root_not_another_record_of_its_key(app, rows, kind, with_aki):
    from api.v2.certificates.export import _resolve_issuer_cert
    pki = build_cross_pki()
    child = pki.int_b if with_aki else _child_without_aki(f'No AKI export {pki.tag}', pki.name_b, pki.key_b)
    with app.app_context():
        _store(rows, (_same_key_record(pki, kind), 'other'), (pki.root_b, 'root'))
        assert _resolve_issuer_cert(child) == pki.root_b


def test_the_opnsense_file_importer_chains_a_ca_listed_before_its_parent(app, rows, monkeypatch, tmp_path):
    from services.opnsense import importer
    monkeypatch.setattr(importer, '__file__', str(tmp_path / 'services' / 'opnsense' / 'importer.py'))
    pki = build_cross_pki()

    def entry(cert, is_root):
        return {'refid': uuid.uuid4().hex[:13], 'descr': f'file import {pki.tag}', 'is_root': is_root,
                'crt': base64.b64encode(pem(cert).encode()).decode(),
                'subject': cert.subject.rfc4514_string(), 'issuer': cert.issuer.rfc4514_string()}
    child, root = entry(pki.int_b, False), entry(pki.root_b, True)
    with app.app_context():
        assert importer.ImportMixin().import_cas([child, root])['imported'] == 2
        stored = {e['refid']: CA.query.filter_by(refid=e['refid']).one() for e in (child, root)}
        rows.extend(r.id for r in stored.values())
        assert stored[child['refid']].caref == root['refid']
        assert stored[root['refid']].caref is None

