"""GET /api/v2/dashboard/health carries the TSA signer's state when the TSA is enabled,
and the expiry horizon flags the delegated OCSP responder certificates."""
import pytest

from models import CA, Certificate, SystemConfig, db
from tests.conftest import get_json

URL = '/api/v2/dashboard/health'
TS_OID = '1.3.6.1.5.5.7.3.8'
KEYS = ('tsa_enabled', 'tsa_signer_cert_refid', 'tsa_ca_refid')


def _clear(app):
    with app.app_context():
        SystemConfig.query.filter(SystemConfig.key.in_(KEYS)).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture
def tsa_config(app):
    _clear(app)

    def put(**cfg):
        with app.app_context():
            for k, v in cfg.items():
                row = SystemConfig.query.filter_by(key=k).first() or SystemConfig(key=k)
                row.value = v
                db.session.add(row)
            db.session.commit()
    yield put
    _clear(app)


def _tsa(auth_client):
    r = auth_client.get(URL)
    assert r.status_code == 200, r.data
    return get_json(r)['data']['protocols'].get('tsa')


def test_absent_when_the_tsa_is_disabled(auth_client, tsa_config):
    tsa_config(tsa_enabled='false')
    assert _tsa(auth_client) is None


def test_ca_certificate_path_is_healthy(app, auth_client, tsa_config, create_ca):
    ca = create_ca(cn='tsa-health-ca')
    with app.app_context():
        refid = db.session.get(CA, ca['id']).refid
    tsa_config(tsa_enabled='true', tsa_signer_cert_refid='', tsa_ca_refid=refid)
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['alert']) == ('ca_certificate', False)


def test_enabled_without_any_signer_is_an_alert(auth_client, tsa_config):
    tsa_config(tsa_enabled='true', tsa_signer_cert_refid='')
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['alert']) == ('no_signer', True)


def test_healthy_dedicated_signer(auth_client, tsa_config, create_cert):
    signer = create_cert(cn='tsa-health-ok', validity_days=365, extra_ekus=[TS_OID])
    tsa_config(tsa_enabled='true', tsa_signer_cert_refid=signer['refid'])
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['alert']) == ('dedicated', False)
    assert tsa['days_left'] > 300


def test_signer_near_expiry_is_an_alert(auth_client, tsa_config, create_cert):
    signer = create_cert(cn='tsa-health-near', validity_days=10, extra_ekus=[TS_OID])
    tsa_config(tsa_enabled='true', tsa_signer_cert_refid=signer['refid'])
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['alert']) == ('expiring', True)
    assert 0 < tsa['days_left'] <= 10


def test_revoked_signer_is_unusable(app, auth_client, tsa_config, create_cert):
    signer = create_cert(cn='tsa-health-revoked', validity_days=200, extra_ekus=[TS_OID])
    tsa_config(tsa_enabled='true', tsa_signer_cert_refid=signer['refid'])
    with app.app_context():
        Certificate.query.filter_by(refid=signer['refid']).first().revoked = True
        db.session.commit()
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['reason'], tsa['alert']) == ('unusable', 'revoked', True)
    assert signer['refid'] not in str(tsa)


def test_signer_without_its_key_is_unusable(app, auth_client, tsa_config, create_cert):
    signer = create_cert(cn='tsa-health-nokey', validity_days=200, extra_ekus=[TS_OID])
    tsa_config(tsa_enabled='true', tsa_signer_cert_refid=signer['refid'])
    with app.app_context():
        Certificate.query.filter_by(refid=signer['refid']).first().prv = None
        db.session.commit()
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['reason'], tsa['alert']) == ('unusable', 'key_unavailable', True)


def test_a_failing_check_is_not_reported_healthy(auth_client, tsa_config, monkeypatch):
    import services.tsa_service as tsa_service
    tsa_config(tsa_enabled='true')
    monkeypatch.setattr(tsa_service, 'describe_configured_signer',
                        lambda: (_ for _ in ()).throw(RuntimeError('boom')))
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['alert']) == ('unavailable', True)
    assert 'boom' not in str(tsa)


def test_expiring_certs_flag_a_delegated_ocsp_responder(app, auth_client, create_cert):
    responder = create_cert(cn='horizon-ocsp-responder', validity_days=20)
    plain = create_cert(cn='horizon-not-a-responder', validity_days=20)
    key = 'ocsp_responder_cert_987654'
    with app.app_context():
        db.session.add(SystemConfig(key=key, value=responder['refid']))
        db.session.commit()
    try:
        r = auth_client.get('/api/v2/dashboard/expiring-certs?limit=200')
        by_refid = {c['refid']: c for c in get_json(r)['data']}
        assert by_refid[responder['refid']]['is_ocsp_responder'] is True
        assert by_refid[plain['refid']]['is_ocsp_responder'] is False
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key=key).delete(synchronize_session=False)
            db.session.commit()
