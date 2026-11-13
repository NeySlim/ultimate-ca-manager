"""An imported CA is chained under the stored CA whose key signed it, whatever the order of the batch."""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import NameOID

from models import CA, db
from tests.fixtures.cross_pki import make_cert, new_key, pem
from tests.test_import_weak_ca_key import _forget_cas, _opnsense, _row  # noqa: F401  (fixture reused)


@pytest.mark.parametrize('mid_first', [True, False])
def test_opnsense_route_links_the_chain_whatever_the_order(app, auth_client, monkeypatch, mid_first):
    tag = uuid.uuid4().hex[:8]
    k_root, k_mid, k_sub = new_key(), new_key(), new_key()
    root = make_cert(f'Root {tag}', k_root)
    mid = make_cert(f'Mid {tag}', k_mid, f'Root {tag}', k_root, path_length=1)
    sub = make_cert(f'Sub {tag}', k_sub, f'Mid {tag}', k_mid, path_length=0)
    rows = {'root': _row(root, f'root {tag}'), 'mid': _row(mid, f'mid {tag}'), 'sub': _row(sub, f'sub {tag}')}
    order = ['root', 'mid', 'sub'] if mid_first else ['root', 'sub', 'mid']
    body = _opnsense(auth_client, monkeypatch, [rows[n] for n in order])
    assert body['imported']['cas'] == 3
    with app.app_context():
        got = {n: CA.query.filter_by(descr=f'{n} {tag}').one() for n in rows}
        assert got['root'].caref is None
        assert got['mid'].caref == got['root'].refid
        assert got['sub'].caref == got['mid'].refid


def _without_aki(subject_cn, subject_key, issuer_cn, issuer_key):
    now = datetime.now(timezone.utc)
    name = lambda cn: x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])  # noqa: E731
    return (x509.CertificateBuilder().subject_name(name(subject_cn)).issuer_name(name(issuer_cn))
            .public_key(subject_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=300))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(issuer_key, hashes.SHA256()))


def _store(cert, descr):
    ca = CA(refid=uuid.uuid4().hex[:16], descr=descr, crt=base64.b64encode(pem(cert).encode()).decode(),
            subject=cert.subject.rfc4514_string(), issuer=cert.issuer.rfc4514_string(),
            serial_number=str(cert.serial_number), imported_from='manual')
    db.session.add(ca)
    db.session.commit()
    return ca


def test_smart_import_links_to_the_namesake_whose_key_signed(app):
    from services.smart_import.importer import SmartImporter
    tag = uuid.uuid4().hex[:8]
    name = f'Twin {tag}'
    k1, k2, k_child = new_key(), new_key(), new_key()
    with app.app_context():
        _store(make_cert(name, k1), 'first twin')
        second = _store(make_cert(name, k2), 'second twin')
        child = _without_aki(f'Child {tag}', k_child, name, k2)
        result = SmartImporter().execute(pem(child))
        assert result.cas_imported == 1, result.errors
        assert CA.query.filter_by(descr=f'Child {tag}').one().caref == second.refid


@pytest.mark.parametrize('order', [('root', 'mid', 'sub'), ('sub', 'mid', 'root'), ('mid', 'root', 'sub')])
def test_smart_import_links_the_chain_whatever_the_order(app, order):
    from services.smart_import.importer import SmartImporter
    tag = uuid.uuid4().hex[:8]
    k_root, k_mid, k_sub = new_key(), new_key(), new_key()
    certs = {'root': make_cert(f'Root {tag}', k_root),
             'mid': make_cert(f'Mid {tag}', k_mid, f'Root {tag}', k_root, path_length=1),
             'sub': make_cert(f'Sub {tag}', k_sub, f'Mid {tag}', k_mid, path_length=0)}
    with app.app_context():
        result = SmartImporter().execute(''.join(pem(certs[n]) for n in order))
        assert result.cas_imported == 3, result.errors
        got = {n: CA.query.filter_by(descr=f'{n.capitalize()} {tag}').one() for n in certs}
        assert got['root'].caref is None
        assert got['mid'].caref == got['root'].refid
        assert got['sub'].caref == got['mid'].refid
