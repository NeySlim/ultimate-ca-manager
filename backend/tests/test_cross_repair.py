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


def test_a_collision_without_a_self_signed_is_reported_with_restore_primary(app, auth_client):
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
    assert found[0]['actions'] == ['restore_primary']
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


# --- review fixes ---------------------------------------------------------------------------

def _set_config(**values):
    from models import SystemConfig
    for key, value in values.items():
        db.session.add(SystemConfig(key=key.replace('__', '.'), value=value))
    db.session.commit()


def _config(key):
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=key).first()
    return row.value if row else None


def test_convert_moves_the_ca_settings_to_the_root(app, auth_client):
    from models import SystemConfig
    pki, ids = _world(app)
    with app.app_context():
        x_ref, b_ref = db.session.get(CA, ids['x']).refid, db.session.get(CA, ids['b']).refid
        for key in ('acme.issuing_ca_id', 'est_ca_refid', 'tsa_ca_refid', 'wstep_ca_refid',
                    'xcep_ca_refid', 'mtls_trusted_ca_id'):
            SystemConfig.query.filter_by(key=key).delete()
        _set_config(acme__issuing_ca_id=x_ref, est_ca_refid=x_ref, tsa_ca_refid=x_ref, wstep_ca_refid=x_ref,
                    xcep_ca_refid=x_ref, mtls_trusted_ca_id=x_ref)
        _set_config(**{f"ocsp_responder_cert_{ids['x']}": '77'})
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    with app.app_context():
        for key in ('acme.issuing_ca_id', 'est_ca_refid', 'tsa_ca_refid', 'wstep_ca_refid',
                    'xcep_ca_refid', 'mtls_trusted_ca_id'):
            assert _config(key) == b_ref, key
        assert _config(f"ocsp_responder_cert_{ids['b']}") == '77'
        assert _config(f"ocsp_responder_cert_{ids['x']}") is None
        for key in ('acme.issuing_ca_id', 'est_ca_refid', 'tsa_ca_refid', 'wstep_ca_refid',
                    'xcep_ca_refid', 'mtls_trusted_ca_id', f"ocsp_responder_cert_{ids['b']}"):
            SystemConfig.query.filter_by(key=key).delete()
        db.session.commit()


def test_urls_embedded_by_the_removed_duplicate_still_resolve(app, auth_client, client):
    pki, ids = _world(app)
    with app.app_context():
        x = db.session.get(CA, ids['x'])
        x.url_slug = f'dup-{pki.tag}'
        db.session.commit()
        x_ref, x_slug = x.refid, x.url_slug
        b_ref = db.session.get(CA, ids['b']).refid
    assert client.get(f'/ca/{x_ref}.cer').status_code == 200
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    with app.app_context():
        db.session.get(CA, ids['b']).cdp_enabled = True
        db.session.commit()
    assert client.get(f'/cdp/{b_ref}.crl').status_code == 200
    root_der = client.get(f'/ca/{b_ref}.cer').data
    for ref in (x_ref, x_slug):
        r = client.get(f'/ca/{ref}.cer')
        assert r.status_code == 200 and r.data == root_der, ref
        assert client.get(f'/cdp/{ref}.crl').status_code == 200, ref
    assert client.get('/ca/00000000-0000-0000-0000-000000000000.cer').status_code == 404


def _limited_client(app, permissions):
    from models import User
    from models.rbac import CustomRole
    name = f'limited-{uuid.uuid4().hex[:8]}'
    admin = app.test_client()
    admin.post('/api/v2/auth/login', json={'username': 'admin', 'password': 'changeme123'})
    r = admin.post('/api/v2/users', json={'username': name, 'password': 'LimitedPass123!',
                                          'email': f'{name}@test.local', 'role': 'viewer'})
    assert r.status_code in (200, 201), r.data
    with app.app_context():
        role = CustomRole(name=name, permissions=permissions)
        db.session.add(role)
        db.session.flush()
        User.query.filter_by(username=name).update({'custom_role_id': role.id})
        db.session.commit()
    c = app.test_client()
    assert c.post('/api/v2/auth/login', json={'username': name, 'password': 'LimitedPass123!'}).status_code == 200
    return c


def test_convert_needs_the_delete_permission_it_exercises(app, auth_client):
    pki, ids = _world(app)
    writer = _limited_client(app, ['read:cas', 'write:cas'])
    assert writer.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 403
    with app.app_context():
        assert db.session.get(CA, ids['x']) is not None
    full = _limited_client(app, ['read:cas', 'write:cas', 'delete:cas'])
    assert full.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200


def test_convert_removes_the_files_and_announces_the_deletion(app, auth_client, monkeypatch):
    from services import webhook_service
    sent, removed = [], []
    monkeypatch.setattr(webhook_service, 'emit_ca_deleted', lambda ca, actor=None: sent.append(ca['id']))
    monkeypatch.setattr('services.ca.helpers.delete_ca_files', lambda ca: removed.append(ca.refid))
    pki, ids = _world(app)
    with app.app_context():
        x_ref = db.session.get(CA, ids['x']).refid
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    assert sent == [ids['x']] and removed == [x_ref]


def test_convert_of_a_duplicate_already_attached_as_cross_certificate_succeeds(app, auth_client):
    pki, ids = _world(app)
    r = auth_client.post(f"/api/v2/cas/{ids['b']}/cross-certificates", json={'certificate': pem(pki.cross_b)})
    assert r.status_code == 201, r.data
    r = auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert db.session.get(CA, ids['x']) is None
        assert CACrossCertificate.query.filter_by(ca_id=ids['b']).count() == 1
        assert db.session.get(CA, ids['i']).caref == db.session.get(CA, ids['b']).refid


def test_success_message_does_not_tell_to_recover_what_was_just_restored(app, auth_client):
    pki, ids = _world(app, with_root_b=False)
    r = auth_client.post(f"/api/v2/cas/{ids['x']}/restore-primary", json={'certificate': pem(pki.root_b)})
    assert r.status_code == 200
    assert 'backup' not in r.get_json()['message']


def test_refusal_and_findings_point_to_restore_primary_only(app, auth_client):
    pki, ids = _world(app, with_root_b=False)
    r = auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={})
    assert r.status_code == 409
    message = r.get_json()['message']
    assert 'backup' in message and 'restore-primary' in message and 'import' not in message
    _, body = _findings(auth_client, pki)
    assert 'import' not in body['note']


def test_the_unexpired_root_is_the_one_a_duplicate_is_converted_onto(app, auth_client):
    from datetime import datetime, timedelta, timezone
    from tests.fixtures.cross_pki import make_cert
    pki, ids = _world(app, with_root_b=False)
    with app.app_context():
        old = make_cert(pki.name_b, pki.key_b, days=-5,
                        not_before=datetime.now(timezone.utc) - timedelta(days=400))
        old_id = _row(old, 'expired root')
        new_id = _row(pki.root_b, 'current root')
    r = auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert CACrossCertificate.query.filter_by(ca_id=new_id).count() == 1
        assert CACrossCertificate.query.filter_by(ca_id=old_id).count() == 0
        assert db.session.get(CA, ids['i']).caref == db.session.get(CA, new_id).refid


def test_a_lost_root_collision_offers_restore_primary(app, auth_client):
    pki = build_cross_pki()
    with app.app_context():
        a = _row(pki.root_a, pki.name_a, pki.key_a)
        ref = db.session.get(CA, a).refid
        _row(pki.cross_b, 'one', pki.key_b, caref=ref)
        from tests.fixtures.cross_pki import make_cert
        _row(make_cert(pki.name_b, pki.key_b, pki.name_a, pki.key_a, days=200), 'two', pki.key_b, caref=ref)
    found, _ = _findings(auth_client, pki)
    assert found[0]['actions'] == ['restore_primary']
