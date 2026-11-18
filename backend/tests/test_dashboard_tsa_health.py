"""GET /api/v2/dashboard/health carries the TSA signer's state when the TSA is enabled,
and the expiry horizon flags the delegated OCSP responder certificates."""
import pytest

from models import CA, Certificate, SystemConfig, db
from tests.conftest import get_json

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

URL = '/api/v2/dashboard/health'
TS_OID = '1.3.6.1.5.5.7.3.8'
KEYS = ('tsa_enabled', 'tsa_signer_cert_refid', 'tsa_ca_refid', 'tsa_require_dedicated_cert')


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


def test_ca_certificate_signing_is_a_warning(app, auth_client, tsa_config, create_ca):
    # The compatibility mode a 2.x upgrade keeps: tokens that fail RFC 3161 §2.3
    ca = create_ca(cn='tsa-health-ca')
    with app.app_context():
        refid = db.session.get(CA, ca['id']).refid
    tsa_config(tsa_enabled='true', tsa_signer_cert_refid='', tsa_ca_refid=refid,
               tsa_require_dedicated_cert='false')
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['alert'], tsa['severity']) == ('ca_certificate', True, 'warning')


def test_a_ca_without_a_dedicated_signer_is_not_configured_by_default(
        app, auth_client, tsa_config, create_ca):
    ca = create_ca(cn='tsa-health-ca-strict')
    with app.app_context():
        refid = db.session.get(CA, ca['id']).refid
    tsa_config(tsa_enabled='true', tsa_signer_cert_refid='', tsa_ca_refid=refid)
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['alert'], tsa['severity']) == ('no_signer', False, None)


def test_enabled_without_any_signer_is_not_an_alert(auth_client, tsa_config):
    tsa_config(tsa_enabled='true', tsa_signer_cert_refid='')
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['alert']) == ('no_signer', False)


def test_untouched_install_is_not_configured_without_alert(auth_client, tsa_config):
    # No tsa_enabled row (on by default) and no tsa_ca_refid: nothing to sign with, nothing broken
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['alert'], tsa['severity']) == ('no_signer', False, None)


def test_healthy_dedicated_signer(auth_client, tsa_config, create_cert):
    signer = create_cert(cn='tsa-health-ok', validity_days=365, extra_ekus=[TS_OID])
    tsa_config(tsa_enabled='true', tsa_signer_cert_refid=signer['refid'])
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['alert'], tsa['severity']) == ('dedicated', False, None)
    assert tsa['days_left'] > 300


def test_a_dedicated_signer_clears_the_warning_with_the_setting_still_off(auth_client, tsa_config, create_cert):
    # The UPGRADE note: the warning lasts until a signer is issued, the setting is switched back after
    signer = create_cert(cn='tsa-health-compat', validity_days=365, extra_ekus=[TS_OID])
    tsa_config(tsa_enabled='true', tsa_signer_cert_refid=signer['refid'], tsa_require_dedicated_cert='false')
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['alert'], tsa['severity']) == ('dedicated', False, None)


def test_signer_near_expiry_is_an_alert(auth_client, tsa_config, create_cert):
    signer = create_cert(cn='tsa-health-near', validity_days=10, extra_ekus=[TS_OID])
    tsa_config(tsa_enabled='true', tsa_signer_cert_refid=signer['refid'])
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['alert'], tsa['severity']) == ('expiring', True, 'critical')
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
        db.session.add(SystemConfig(key=key, value=str(responder['id'])))
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


def test_a_failed_statement_in_the_check_leaves_the_session_usable(app, tsa_config, monkeypatch):
    # On PostgreSQL a failed statement aborts the transaction until a rollback
    from sqlalchemy import text
    import services.tsa_service as tsa_service
    from services import dashboard_aggregates
    tsa_config(tsa_enabled='true')

    def broken():
        db.session.execute(text('SELECT * FROM tsa_health_no_such_table'))
    monkeypatch.setattr(tsa_service, 'describe_configured_signer', broken)
    with app.test_request_context(URL):
        assert dashboard_aggregates._tsa_health()['state'] == 'unavailable'
        assert SystemConfig.query.filter_by(key='tsa_enabled').first().value == 'true'


def _reference_tsa_rows():
    """The `tsa` state table of docs/API_REFERENCE.md: {state: (alert, severity)}."""
    import os
    import re
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(repo, 'docs', 'API_REFERENCE.md'), encoding='utf-8') as fh:
        lines = fh.read().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith('| `tsa` state |'))
    rows = {}
    for line in lines[start + 2:]:
        if not line.startswith('|'):
            break
        cells = [c.strip() for c in line.strip('|').split('|')]
        severity = cells[3].strip('`')
        rows[cells[0].strip('`')] = (cells[2] == 'true', None if severity == 'null' else severity)
    return rows


def test_the_reference_names_every_state_the_route_returns(
        app, auth_client, tsa_config, create_ca, create_cert, monkeypatch):
    import services.tsa_service as tsa_service
    seen = {}

    def record():
        tsa = _tsa(auth_client)
        seen[tsa['state']] = (tsa['alert'], tsa['severity'])

    tsa_config(tsa_enabled='true', tsa_signer_cert_refid='')
    record()
    ca = create_ca(cn='tsa-health-ref-ca')
    with app.app_context():
        refid = db.session.get(CA, ca['id']).refid
    tsa_config(tsa_ca_refid=refid, tsa_require_dedicated_cert='false')
    record()
    tsa_config(tsa_signer_cert_refid=create_cert(
        cn='tsa-health-ref-ok', validity_days=365, extra_ekus=[TS_OID])['refid'])
    record()
    tsa_config(tsa_signer_cert_refid=create_cert(
        cn='tsa-health-ref-near', validity_days=10, extra_ekus=[TS_OID])['refid'])
    record()
    revoked = create_cert(cn='tsa-health-ref-revoked', validity_days=200, extra_ekus=[TS_OID])
    with app.app_context():
        Certificate.query.filter_by(refid=revoked['refid']).first().revoked = True
        db.session.commit()
    tsa_config(tsa_signer_cert_refid=revoked['refid'])
    record()
    monkeypatch.setattr(tsa_service, 'describe_configured_signer',
                        lambda: (_ for _ in ()).throw(RuntimeError('boom')))
    record()
    assert seen == _reference_tsa_rows()


def test_a_ca_whose_key_cannot_sign_tokens_is_not_reported_signing(app, auth_client, tsa_config, create_ca):
    # /tsa answers 503 for such a CA: the overview must not say the CA certificate signs
    ca = create_ca(cn='tsa-health-ed25519', keyAlgo='EdDSA', keySize='Ed25519')
    with app.app_context():
        refid = db.session.get(CA, ca['id']).refid
    tsa_config(tsa_enabled='true', tsa_signer_cert_refid='', tsa_ca_refid=refid,
               tsa_require_dedicated_cert='false')
    tsa = _tsa(auth_client)
    assert (tsa['state'], tsa['alert'], tsa['severity']) == ('no_signer', False, None)


def test_expiring_certs_flag_a_signer_stored_with_blanks(auth_client, tsa_config, create_cert):
    signer = create_cert(cn='tsa-health-padded-signer', validity_days=20)
    tsa_config(tsa_signer_cert_refid=f"  {signer['refid']}\n")
    r = auth_client.get('/api/v2/dashboard/expiring-certs?limit=200')
    by_refid = {c['refid']: c for c in get_json(r)['data']}
    assert by_refid[signer['refid']]['is_tsa_signer'] is True
