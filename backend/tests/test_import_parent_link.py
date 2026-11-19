"""An imported CA is chained under the stored CA whose key signed it, whatever the order of the batch."""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from models import CA, SystemConfig, db
from tests.fixtures.cross_pki import key_pem, make_cert, new_key, pem
from tests.test_opnsense_import import _Session


@pytest.fixture(autouse=True)
def _forget_cas(app):
    with app.app_context():
        before = {c.id for c in CA.query.all()}
    yield
    with app.app_context():
        # ORM delete: SQLite tests run without foreign keys, so a bulk delete would orphan cross rows
        for ca in CA.query.filter(~CA.id.in_(before)).all():
            db.session.delete(ca)
        db.session.commit()


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if value is None:
        if row:
            db.session.delete(row)
    elif row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


def _cn(cert):
    return cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value


@pytest.mark.parametrize('endpoint', ['/api/v2/cas/import', '/api/v2/certificates/import'])
def test_imported_child_ca_is_linked_to_its_imported_parent_at_once(app, client, auth_client, endpoint):
    """Parent known from the import response on, and GetCACert in chain mode serves both
    certificates without waiting for the hourly backfill."""
    tag = uuid.uuid4().hex[:6]
    root_key, child_key = new_key('rsa'), new_key('rsa')  # SCEP encrypts to an RSA key
    root_cn, child_cn = f'Import Root {tag}', f'Import Child {tag}'
    root = make_cert(root_cn, root_key)
    child = make_cert(child_cn, child_key, root_cn, root_key, path_length=0)
    ids, refids = [], []
    with app.app_context():
        saved = {k: (row.value if (row := SystemConfig.query.filter_by(key=k).first()) else None)
                 for k in ('scep_enabled', 'scep_ca_id', 'scep_getcacert_chain')}
    try:
        for cert, key in ((root, root_key), (child, child_key)):
            r = auth_client.post(endpoint, data={'pem_content': pem(cert) + key_pem(key)},
                                 content_type='multipart/form-data')
            assert r.status_code in (200, 201), r.data
            data = json.loads(r.data)['data']
            # The response itself names the parent
            assert data['caref'] == (refids[0] if refids else None)
            ids.append(data['id'])
            refids.append(data['refid'])
        with app.app_context():
            root, child = db.session.get(CA, ids[0]), db.session.get(CA, ids[1])
            assert child.caref == root.refid
            assert root.caref is None
            _set('scep_enabled', 'true')
            _set('scep_ca_id', str(ids[1]))
            _set('scep_getcacert_chain', 'true')
        r = client.get('/scep/pkiclient.exe?operation=GetCACert')
        assert r.status_code == 200, r.data
        assert {_cn(c) for c in pkcs7.load_der_pkcs7_certificates(r.data)} == {root_cn, child_cn}
    finally:
        with app.app_context():
            for k, v in saved.items():
                _set(k, v)


def _row(cert, descr):
    return {'uuid': str(uuid.uuid4()), 'refid': uuid.uuid4().hex[:13], 'descr': descr,
            'crt': base64.b64encode(pem(cert).encode()).decode(), 'serial': '1'}


@pytest.mark.parametrize('mid_first', [True, False])
def test_opnsense_route_links_the_chain_whatever_the_order(app, auth_client, monkeypatch, mid_first):
    from api.v2 import import_opnsense
    tag = uuid.uuid4().hex[:8]
    k_root, k_mid, k_sub = new_key(), new_key(), new_key()
    root = make_cert(f'Root {tag}', k_root)
    mid = make_cert(f'Mid {tag}', k_mid, f'Root {tag}', k_root, path_length=1)
    sub = make_cert(f'Sub {tag}', k_sub, f'Mid {tag}', k_mid, path_length=0)
    rows = {'root': _row(root, f'root {tag}'), 'mid': _row(mid, f'mid {tag}'), 'sub': _row(sub, f'sub {tag}')}
    order = ['root', 'mid', 'sub'] if mid_first else ['root', 'sub', 'mid']
    # selected_ids is a set: make it a list so the rows are handled in the order given, and record it
    monkeypatch.setattr(import_opnsense, 'set', list, raising=False)
    seen = []
    real_attach = import_opnsense.cross_certs.attach_to_counterpart
    monkeypatch.setattr(import_opnsense.cross_certs, 'attach_to_counterpart',
                        lambda crt, *a, **k: (seen.append(next(n for n, r in rows.items() if r['crt'] == crt)),
                                              real_attach(crt, *a, **k))[1])
    monkeypatch.setattr(import_opnsense, 'create_session',
                        lambda verify_ssl=True: _Session([rows[n] for n in order], []))
    r = auth_client.post('/api/v2/import/opnsense/import', json={
        'host': '192.0.2.10', 'port': 443, 'api_key': 'k', 'api_secret': 's',
        'verify_ssl': False, 'items': [rows[n]['uuid'] for n in order]})
    assert r.status_code == 200, r.data
    assert seen == order
    assert json.loads(r.data)['data']['imported']['cas'] == 3
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


@pytest.mark.parametrize('unsupported_key', [False, True])
def test_smart_import_keeps_the_name_link_when_no_signature_verifies(app, monkeypatch, unsupported_key):
    """No stored CA verifies the signature (another key, or a key type not handled here):
    the issuer name still links it, as before."""
    from services.smart_import.importer import SmartImporter
    from utils import cert_issuer
    tag = uuid.uuid4().hex[:8]
    name = f'Namesake {tag}'
    parent_key = new_key()
    if unsupported_key:
        def cannot_check(cert, issuer):
            raise cert_issuer.UnsupportedIssuerKey('key type not handled')
        monkeypatch.setattr(cert_issuer, 'certificate_signed_by', cannot_check)
    with app.app_context():
        stored = _store(make_cert(name, parent_key), 'namesake')
        child = _without_aki(f'Orphan {tag}', new_key(), name, parent_key if unsupported_key else new_key())
        result = SmartImporter().execute(pem(child))
        assert result.cas_imported == 1, result.errors
        assert CA.query.filter_by(descr=f'Orphan {tag}').one().caref == stored.refid


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
