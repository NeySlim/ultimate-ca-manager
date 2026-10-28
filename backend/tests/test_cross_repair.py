"""Phase 5: findings on databases touched by the pre-#400 import paths, and the two explicit repairs."""
import base64
import uuid

from cryptography import x509

from models import CA, db
from models.ca_cross_certificate import CACrossCertificate
from services.ski_aki_backfill import backfill_ski_aki
from tests.fixtures.cross_pki import build_cross_pki, key_pem, openssl_verify, pem
from utils.key_codec import store_pem_bytes

FINDINGS = '/api/v2/cas/cross-findings'


def _row(cert, descr, key=None, caref=None):
    ski = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.key_identifier
    row = CA(refid=str(uuid.uuid4()), descr=descr, serial=0,
             crt=base64.b64encode(pem(cert).encode()).decode(),
             prv=store_pem_bytes(key_pem(key).encode()) if key else None, caref=caref,
             subject=cert.subject.rfc4514_string(), issuer=cert.issuer.rfc4514_string(),
             serial_number=str(cert.serial_number), ski=ski.hex(':').upper())
    db.session.add(row)
    db.session.commit()
    return row.id


def _world(app, with_root_b=True, key_on_root_b=False):
    """Root A, the cross certificate recorded as a CA under A, optionally the self-signed B, Int B under the cross."""
    pki = build_cross_pki()
    with app.app_context():
        a = _row(pki.root_a, pki.name_a, pki.key_a)
        a_ref = db.session.get(CA, a).refid
        x = _row(pki.cross_b, f'{pki.name_b} cross', pki.key_b, caref=a_ref)
        b = _row(pki.root_b, pki.name_b, pki.key_b if key_on_root_b else None) if with_root_b else None
        x_ref = db.session.get(CA, x).refid
        i = _row(pki.int_b, f'Cross Int B {pki.tag}', pki.key_int, caref=x_ref)
    return pki, {'a': a, 'x': x, 'b': b, 'i': i}


def _findings(auth_client, pki):
    r = auth_client.get(FINDINGS)
    assert r.status_code == 200, r.data
    body = r.get_json()['data']
    return [f for f in body['findings'] if pki.tag in (f.get('subject') or '')], body


def test_a_shadowed_root_is_reported_with_its_conversion_and_nothing_is_changed(app, auth_client):
    pki, ids = _world(app)
    found, body = _findings(auth_client, pki)
    assert len(found) == 1
    f = found[0]
    assert f['kind'] == 'shadowed_root' and f['ca_id'] == ids['x'] and f['root_id'] == ids['b']
    assert f['actions'] == ['convert_to_cross']
    assert 'backup' in body['note']
    with app.app_context():
        backfill_ski_aki()
        assert db.session.get(CA, ids['x']) is not None and db.session.get(CA, ids['b']) is not None


def test_a_collision_without_a_self_signed_is_reported_without_action(app, auth_client):
    pki = build_cross_pki()
    with app.app_context():
        a = _row(pki.root_a, pki.name_a, pki.key_a)
        ref = db.session.get(CA, a).refid
        _row(pki.cross_b, 'one', pki.key_b, caref=ref)
        # a second certificate over the same key by the same issuer
        from tests.fixtures.cross_pki import make_cert
        _row(make_cert(pki.name_b, pki.key_b, pki.name_a, pki.key_a, days=200), 'two', pki.key_b, caref=ref)
    found, _ = _findings(auth_client, pki)
    assert [f['kind'] for f in found] == ['same_key_distinct_certs']
    assert found[0]['actions'] == []
    assert len(found[0]['ca_ids']) == 2


def test_convert_attaches_the_duplicate_as_cross_certificate_and_keeps_its_children(app, auth_client):
    pki, ids = _world(app)
    r = auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert db.session.get(CA, ids['x']) is None
        root = db.session.get(CA, ids['b'])
        assert root.subject == root.issuer
        rows = CACrossCertificate.query.filter_by(ca_id=ids['b']).all()
        assert [x.serial_number for x in rows] == [str(pki.cross_b.serial_number)]
        assert rows[0].issuer_caref == db.session.get(CA, ids['a']).refid
        assert db.session.get(CA, ids['i']).caref == root.refid
        assert root.prv, 'the key of the removed duplicate is kept on the self-signed record'
        cross = x509.load_pem_x509_certificate(base64.b64decode(rows[0].crt))
    ok, out = openssl_verify(pki.leaf, [pki.root_a], [pki.int_b, cross])
    assert ok, out
    found, _ = _findings(auth_client, pki)
    assert found == []


def test_convert_refuses_a_record_that_is_not_shadowing_a_root(app, auth_client):
    pki, ids = _world(app, with_root_b=False)
    r = auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={})
    assert r.status_code == 409
    assert 'backup' in r.get_json()['message']
    r = auth_client.post(f"/api/v2/cas/{ids['a']}/convert-to-cross", json={})
    assert r.status_code == 409
    with app.app_context():
        assert db.session.get(CA, ids['x']) is not None


def test_restore_primary_puts_the_self_signed_back_and_keeps_the_cross_certificate(app, auth_client):
    pki, ids = _world(app, with_root_b=False)
    r = auth_client.post(f"/api/v2/cas/{ids['x']}/restore-primary", json={'certificate': pem(pki.root_b)})
    assert r.status_code == 200, r.data
    with app.app_context():
        record = db.session.get(CA, ids['x'])
        assert record.subject == record.issuer and not record.caref and record.prv
        assert x509.load_pem_x509_certificate(base64.b64decode(record.crt)) == pki.root_b
        rows = CACrossCertificate.query.filter_by(ca_id=ids['x']).all()
        assert [x.serial_number for x in rows] == [str(pki.cross_b.serial_number)]
        cross = x509.load_pem_x509_certificate(base64.b64decode(rows[0].crt))
    ok, out = openssl_verify(pki.leaf, [pki.root_b], [pki.int_b])
    assert ok, out
    ok, out = openssl_verify(pki.leaf, [pki.root_a], [pki.int_b, cross])
    assert ok, out


def test_restore_primary_refuses_a_foreign_or_non_self_signed_certificate(app, auth_client):
    pki, ids = _world(app, with_root_b=False)
    other = build_cross_pki()
    cases = ((pem(other.root_b), 'subject or key'), (pem(pki.cross_b), 'self-signed'), ('not a certificate', 'parsed'))
    for bad, expected in cases:
        r = auth_client.post(f"/api/v2/cas/{ids['x']}/restore-primary", json={'certificate': bad})
        assert r.status_code in (400, 409), (bad[:30], r.data)
        assert expected in r.get_json()['message'], r.data
    with app.app_context():
        assert db.session.get(CA, ids['x']).issuer == pki.cross_b.issuer.rfc4514_string()


def test_restore_primary_refuses_when_a_self_signed_record_is_held(app, auth_client):
    pki, ids = _world(app)
    r = auth_client.post(f"/api/v2/cas/{ids['x']}/restore-primary", json={'certificate': pem(pki.root_b)})
    assert r.status_code == 409
    assert 'convert' in r.get_json()['message']


def test_repairs_need_authentication(app, client):
    assert client.get(FINDINGS).status_code in (401, 403)
    assert client.post('/api/v2/cas/1/convert-to-cross', json={}).status_code in (401, 403)
    assert client.post('/api/v2/cas/1/restore-primary', json={}).status_code in (401, 403)
