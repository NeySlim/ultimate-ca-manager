"""Phase 5: findings on databases touched by the pre-#400 import paths, and the two explicit repairs."""
import base64
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from models import CA, db
from models.ca_cross_certificate import CACrossCertificate
from services.ca import cross_certs
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
                    'xcep_ca_refid', 'mtls_trusted_ca_id', 'scep_ca_id'):
            SystemConfig.query.filter_by(key=key).delete()
        _set_config(acme__issuing_ca_id=x_ref, est_ca_refid=x_ref, tsa_ca_refid=x_ref, wstep_ca_refid=x_ref,
                    xcep_ca_refid=x_ref, mtls_trusted_ca_id=x_ref, scep_ca_id=str(ids['x']))
        _set_config(**{f"ocsp_responder_cert_{ids['x']}": '77'})
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    with app.app_context():
        for key in ('acme.issuing_ca_id', 'est_ca_refid', 'tsa_ca_refid', 'wstep_ca_refid',
                    'xcep_ca_refid', 'mtls_trusted_ca_id'):
            assert _config(key) == b_ref, key
        assert _config('scep_ca_id') == str(ids['b'])
        assert _config(f"ocsp_responder_cert_{ids['b']}") == '77'
        assert _config(f"ocsp_responder_cert_{ids['x']}") is None
        for key in ('acme.issuing_ca_id', 'est_ca_refid', 'tsa_ca_refid', 'wstep_ca_refid',
                    'xcep_ca_refid', 'mtls_trusted_ca_id', 'scep_ca_id', f"ocsp_responder_cert_{ids['b']}"):
            SystemConfig.query.filter_by(key=key).delete()
        db.session.commit()


def test_urls_embedded_by_the_removed_duplicate_still_resolve(app, auth_client, client):
    pki, ids = _world(app)
    with app.app_context():
        x = db.session.get(CA, ids['x'])
        x.url_slug = f'dup-{pki.tag}'
        x.cdp_enabled = True
        db.session.commit()
        x_ref, x_slug = x.refid, x.url_slug
        b_ref = db.session.get(CA, ids['b']).refid
    assert client.get(f'/ca/{x_ref}.cer').status_code == 200
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    assert client.get(f'/cdp/{b_ref}.crl').status_code == 200
    for ref in (x_ref, x_slug, str(ids['x'])):
        assert client.get(f'/cdp/{ref}.crl').status_code == 200, ref
    for ref in (x_ref, x_slug):
        assert client.get(f'/ca/{ref}.cer').status_code == 200, ref
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


def test_convert_keeps_the_revocation_publication_of_the_duplicate(app, auth_client):
    pki, ids = _world(app)
    with app.app_context():
        x, b = db.session.get(CA, ids['x']), db.session.get(CA, ids['b'])
        x.cdp_enabled, x.ocsp_enabled, x.delta_crl_enabled = True, True, True
        x.crl_validity_days, x.crl_publish_interval_hours, x.crl_digest = 3, 6, 'sha384'
        b.cdp_enabled = b.ocsp_enabled = b.delta_crl_enabled = False
        b.crl_validity_days = b.crl_publish_interval_hours = b.crl_digest = None
        db.session.commit()
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    with app.app_context():
        b = db.session.get(CA, ids['b'])
        assert (b.cdp_enabled, b.ocsp_enabled, b.delta_crl_enabled) == (True, True, True)
        assert (b.crl_validity_days, b.crl_publish_interval_hours, b.crl_digest) == (3, 6, 'sha384')


def test_convert_does_not_switch_off_what_the_root_publishes(app, auth_client):
    pki, ids = _world(app)
    with app.app_context():
        b = db.session.get(CA, ids['b'])
        b.cdp_enabled, b.ocsp_enabled, b.crl_validity_days = True, True, 9
        db.session.get(CA, ids['x']).crl_validity_days = 3
        db.session.commit()
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    with app.app_context():
        b = db.session.get(CA, ids['b'])
        assert b.cdp_enabled and b.ocsp_enabled and b.crl_validity_days == 9


def test_the_aia_url_of_the_duplicate_keeps_serving_the_cross_certificate(app, auth_client, client):
    pki, ids = _world(app)
    with app.app_context():
        x_ref = db.session.get(CA, ids['x']).refid
        b_ref = db.session.get(CA, ids['b']).refid
    cross_der = pki.cross_b.public_bytes(serialization.Encoding.DER)
    root_der = pki.root_b.public_bytes(serialization.Encoding.DER)
    assert client.get(f'/ca/{x_ref}.cer').data == cross_der
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    assert client.get(f'/ca/{x_ref}.cer').data == cross_der
    assert x509.load_pem_x509_certificate(client.get(f'/ca/{x_ref}.pem').data) == pki.cross_b
    assert client.get(f'/ca/{b_ref}.cer').data == root_der


def test_convert_moves_the_scep_challenge_with_the_scep_ca(app, auth_client):
    from api.v2.scep import challenge_age_state
    pki, ids = _world(app)
    with app.app_context():
        _set_config(scep_ca_id=str(ids['x']))
        _set_config(**{f"scep_challenge_{ids['x']}": 'secret-x',
                       f"scep_challenge_{ids['x']}_generated_at": '2026-01-01T00:00:00'})
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    with app.app_context():
        assert challenge_age_state(ids['b'])[0] == 'secret-x'
        assert _config(f"scep_challenge_{ids['x']}") is None
        assert _config(f"scep_challenge_{ids['x']}_generated_at") is None
        from models import SystemConfig
        SystemConfig.query.filter(SystemConfig.key.like('scep_%')).delete(synchronize_session=False)
        db.session.commit()


def test_convert_drops_the_challenge_of_a_non_scep_duplicate_when_the_root_has_one(app, auth_client):
    pki, ids = _world(app)
    with app.app_context():
        _set_config(**{f"scep_challenge_{ids['x']}": 'secret-x', f"scep_challenge_{ids['b']}": 'secret-b'})
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    with app.app_context():
        assert _config(f"scep_challenge_{ids['b']}") == 'secret-b'
        assert _config(f"scep_challenge_{ids['x']}") is None
        from models import SystemConfig
        SystemConfig.query.filter(SystemConfig.key.like('scep_challenge_%')).delete(synchronize_session=False)
        db.session.commit()


def test_a_second_conversion_with_a_known_slug_succeeds_and_new_cas_avoid_the_alias_slug(app, auth_client):
    from models import SystemConfig
    from services.ca.ca_creation import CACreationMixin as CAService
    pki, ids = _world(app)
    slug = f'dup-{pki.tag}'.lower()
    with app.app_context():
        b_ref = db.session.get(CA, ids['b']).refid
        db.session.get(CA, ids['x']).url_slug = slug
        db.session.add(SystemConfig(key=f'ca_url_alias_{slug}', value='older-ref'))
        db.session.commit()
        gone = f'gone-{pki.tag}'.lower()
        db.session.add(SystemConfig(key=f'ca_url_alias_{gone}', value='older-ref'))
        db.session.commit()
        assert CAService._unique_url_slug(gone) not in (gone, None)
    r = auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert _config(f'ca_url_alias_{slug}') == b_ref


def test_convert_goes_to_the_root_that_already_carries_the_cross_certificate(app, auth_client):
    from datetime import datetime, timedelta, timezone
    from tests.fixtures.cross_pki import make_cert
    pki, ids = _world(app, with_root_b=False)
    with app.app_context():
        soon = make_cert(pki.name_b, pki.key_b, days=30)
        short_id = _row(soon, 'short root')
        long_id = _row(pki.root_b, 'long root')
        row, _ = cross_certs.attach_certificate(db.session.get(CA, short_id), pki.cross_b, 'test')
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    with app.app_context():
        assert CACrossCertificate.query.filter_by(ca_id=short_id).count() == 1
        assert db.session.get(CA, ids['i']).caref == db.session.get(CA, short_id).refid


def test_an_expired_root_carrying_the_cross_does_not_win_over_the_valid_root(app, auth_client):
    from datetime import datetime, timedelta, timezone
    from tests.fixtures.cross_pki import make_cert
    pki, ids = _world(app, with_root_b=False)
    with app.app_context():
        old = make_cert(pki.name_b, pki.key_b, days=-5,
                        not_before=datetime.now(timezone.utc) - timedelta(days=400))
        old_id = _row(old, 'expired root')
        new_id = _row(pki.root_b, 'current root')
        cross_certs.attach_certificate(db.session.get(CA, old_id), pki.cross_b, 'test')
    r = auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert CACrossCertificate.query.filter_by(ca_id=new_id).count() == 1
        assert CACrossCertificate.query.filter_by(ca_id=old_id).count() == 0
        assert db.session.get(CA, ids['i']).caref == db.session.get(CA, new_id).refid


def test_convert_keeps_the_challenge_of_the_configured_scep_ca_with_its_timestamp(app, auth_client):
    from api.v2.scep import challenge_age_state
    pki, ids = _world(app)
    with app.app_context():
        _set_config(scep_ca_id=str(ids['x']))
        _set_config(**{f"scep_challenge_{ids['x']}": 'live-x',
                       f"scep_challenge_{ids['x']}_generated_at": datetime_now_iso(),
                       f"scep_challenge_{ids['b']}": 'stale-b'})
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    with app.app_context():
        assert challenge_age_state(ids['b'])[0] == 'live-x'
        assert _config(f"scep_challenge_{ids['b']}_generated_at") is not None
        from models import SystemConfig
        SystemConfig.query.filter(SystemConfig.key.like('scep_%')).delete(synchronize_session=False)
        db.session.commit()


def datetime_now_iso():
    from datetime import datetime
    return datetime.now().replace(microsecond=0).isoformat()


@pytest.mark.parametrize('kind', ['frp', 'gost', 'sm2'])
def test_a_ca_with_a_key_pyca_cannot_load_does_not_break_the_findings(app, auth_client, kind):
    from tests.test_tolerant_foreign_algorithms import build_cert, pem as foreign_pem
    pki, ids = _world(app)
    with app.app_context():
        record = CA(refid=str(uuid.uuid4()), descr=f'foreign {kind} {pki.tag}', serial=0,
                    crt=base64.b64encode(foreign_pem(build_cert(kind, f'F {pki.tag}', is_ca=True)).encode()).decode(),
                    subject=f'CN=F {pki.tag}', issuer=f'CN=F {pki.tag}', ski=f'AA:{pki.tag[:2]}')
        db.session.add(record)
        db.session.commit()
    found, _ = _findings(auth_client, pki)
    assert [f['kind'] for f in found] == ['shadowed_root'] and found[0]['ca_id'] == ids['x']
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
