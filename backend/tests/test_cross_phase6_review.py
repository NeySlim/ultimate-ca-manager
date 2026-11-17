"""Review fixes on the cross-certificate repair, chain variants and CA record (#400)."""
import base64
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models import CA, db
from models.ca_cross_certificate import CACrossCertificate
from services.ca import cross_certs
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import build_cross_pki, make_cert, new_key, pem
from tests.test_cross_repair import _world, _row, _set_config, _config


def _served(ca_id):
    return CACrossCertificate.query.filter_by(ca_id=ca_id, served=True).count()


def test_a_cross_moved_off_an_expired_root_does_not_make_two_served_rows(app, auth_client):
    pki, ids = _world(app, with_root_b=False)
    key_c = new_key()
    with app.app_context():
        old = make_cert(pki.name_b, pki.key_b, days=-5,
                        not_before=datetime.now(timezone.utc) - timedelta(days=400))
        old_id = _row(old, 'expired root')
        new_id = _row(pki.root_b, 'current root')
        cross_certs.attach_certificate(db.session.get(CA, old_id), pki.cross_b, 'test', served=True)
        other = make_cert(pki.name_b, pki.key_b, 'Other issuer', key_c, days=200)
        cross_certs.attach_certificate(db.session.get(CA, new_id), other, 'test', served=True)
        assert _served(new_id) == 1
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    with app.app_context():
        assert CACrossCertificate.query.filter_by(ca_id=new_id).count() == 2
        assert _served(new_id) == 1


def test_a_cross_moved_off_an_expired_root_keeps_the_url_of_an_earlier_conversion(app, auth_client):
    from models import AuditLog
    pki, ids = _world(app, with_root_b=False)
    with app.app_context():
        old = make_cert(pki.name_b, pki.key_b, days=-5,
                        not_before=datetime.now(timezone.utc) - timedelta(days=400))
        old_id = _row(old, 'expired root')
        new_id = _row(pki.root_b, 'current root')
        old_ref = db.session.get(CA, old_id).refid
        row, _ = cross_certs.attach_certificate(db.session.get(CA, old_id), pki.cross_b, 'test', served=True)
        _set_config(ca_url_alias_earlier=old_ref, ca_url_cross_earlier=str(row.id))
        row_id = row.id
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    with app.app_context():
        from services.ca import cross_repair
        target = cross_repair.alias_target('earlier')
        assert target.id == new_id
        assert cross_repair.alias_cross('earlier', target).id == row_id
        assert AuditLog.query.filter_by(action='ca_cross_certificate_detached', resource_id=str(old_id)).count() == 1


def test_chain_variants_default_matches_what_a_plain_ca_export_returns(app, auth_client):
    pki = build_cross_pki()
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a))
        SmartImporter().execute(pem(pki.root_b))
        b = CA.query.filter_by(descr=pki.name_b).one().id
    xid = auth_client.post(f'/api/v2/cas/{b}/cross-certificates',
                           json={'certificate': pem(pki.cross_b), 'served': True}).get_json()['data']['id']
    variants = {v['id']: v for v in auth_client.get(f'/api/v2/cas/{b}/chain-variants').get_json()['data']}
    assert variants['primary']['default'] is True and variants[f'cross:{xid}']['default'] is False
    exported = auth_client.get(f'/api/v2/cas/{b}/export?format=pem&include_chain=true').data.decode()
    assert exported.count('BEGIN CERTIFICATE') == 1


def test_a_named_chain_variant_applies_without_include_chain(app, auth_client):
    pki = build_cross_pki()
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a))
        SmartImporter().execute(pem(pki.root_b))
        b = CA.query.filter_by(descr=pki.name_b).one().id
    xid = auth_client.post(f'/api/v2/cas/{b}/cross-certificates',
                           json={'certificate': pem(pki.cross_b)}).get_json()['data']['id']
    url = f'/api/v2/cas/{b}/export?format=pem&include_chain=false'
    assert auth_client.get(url).data.decode().strip() == pem(pki.root_b).strip()
    named = auth_client.get(f'{url}&chain_variant=cross:{xid}')
    assert named.status_code == 200 and named.data.decode().strip() == pem(pki.cross_b).strip()


def test_the_served_flag_of_the_ca_record_ignores_an_expired_row(app, auth_client):
    pki = build_cross_pki()
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a))
        SmartImporter().execute(pem(pki.root_b))
        b = CA.query.filter_by(descr=pki.name_b).one().id
    xid = auth_client.post(f'/api/v2/cas/{b}/cross-certificates',
                           json={'certificate': pem(pki.cross_b), 'served': True}).get_json()['data']['id']
    with app.app_context():
        db.session.get(CACrossCertificate, xid).valid_to = datetime.utcnow() - timedelta(days=1)
        db.session.commit()
    data = auth_client.get(f'/api/v2/cas/{b}').get_json()['data']
    assert data['cross_certificate_count'] == 1 and data['cross_certificate_served'] is False


def test_a_scep_ca_without_challenge_does_not_inherit_a_stale_one_from_the_root(app, auth_client):
    pki, ids = _world(app)
    with app.app_context():
        from models import SystemConfig
        SystemConfig.query.filter(SystemConfig.key.like('scep_%')).delete(synchronize_session=False)
        db.session.commit()
        _set_config(scep_ca_id=str(ids['x']))
        _set_config(**{f"scep_challenge_{ids['b']}": 'stale-b',
                       f"scep_challenge_{ids['b']}_generated_at": '2020-01-01T00:00:00'})
    assert auth_client.post(f"/api/v2/cas/{ids['x']}/convert-to-cross", json={}).status_code == 200
    with app.app_context():
        assert _config(f"scep_challenge_{ids['b']}") is None
        assert _config(f"scep_challenge_{ids['b']}_generated_at") is None
        from models import SystemConfig
        SystemConfig.query.filter(SystemConfig.key.like('scep_%')).delete(synchronize_session=False)
        db.session.commit()


@pytest.mark.parametrize('kind', ['frp', 'gost', 'sm2'])
def test_cross_sign_under_a_root_with_a_key_pyca_cannot_load_is_not_a_500(app, auth_client, kind):
    from tests.test_tolerant_foreign_algorithms import build_cert, pem as foreign_pem
    from tests.fixtures.cross_pki import key_pem
    from utils.key_codec import store_pem_bytes
    pki = build_cross_pki()
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a))
        a = CA.query.filter_by(descr=pki.name_a).one()
        a.prv = store_pem_bytes(key_pem(pki.key_a).encode())
        foreign = CA(refid=str(uuid.uuid4()), descr=f'foreign {kind} {pki.tag}', serial=0,
                     crt=base64.b64encode(foreign_pem(build_cert(kind, f'F {pki.tag}', is_ca=True)).encode()).decode(),
                     subject=f'CN=F {pki.tag}', issuer=f'CN=F {pki.tag}', ski=f'AA:{pki.tag[:2]}')
        db.session.add(foreign)
        db.session.commit()
        sub = CA(refid=str(uuid.uuid4()), descr=f'sub {pki.tag}', serial=0, caref=foreign.refid,
                 crt=base64.b64encode(pem(pki.int_b).encode()).decode(),
                 subject=pki.int_b.subject.rfc4514_string(), issuer=f'CN=F {pki.tag}', ski=f'BB:{pki.tag[:2]}')
        db.session.add(sub)
        db.session.commit()
        a_id, sub_id = a.id, sub.id
    r = auth_client.post(f'/api/v2/cas/{a_id}/cross-sign', json={'subject_ca_id': sub_id})
    assert r.status_code < 500, r.data
