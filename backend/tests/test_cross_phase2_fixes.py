"""Review follow-ups carried into phase 2: sibling-record policies, OPNsense audit timing, persisted revocation (#400)."""
from models import ApprovalRequest, CA, db
from models.ca_cross_certificate import CACrossCertificate
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import build_cross_pki, make_cert, new_key, pem
from tests.test_cross_review_fixes2 import _x, sibling_world  # noqa: F401


def test_a_revocation_policy_on_the_sibling_record_of_the_issuer_still_holds_the_request(
        app, create_user, sibling_world):
    from tests.test_approval_revoke_renew import _drop_policy, _json, _login, _policy
    pki, b, xid, root_id, prime_id = sibling_world
    pid = _policy(app, prime_id, 'xc-sibling', ['revocation'])
    try:
        operator, _ = _login(app, create_user)
        r = _json(operator, 'post', _x(b, xid, '/revoke'), {'reason': 'keyCompromise'})
        assert r.get_json()['data'].get('approval_id'), r.get_json()
        with app.app_context():
            assert ApprovalRequest.query.filter_by(policy_id=pid).count() == 1
            assert not db.session.get(CACrossCertificate, xid).revoked
    finally:
        _drop_policy(app, pid)


def test_a_cross_certificate_revoked_under_a_sibling_record_stays_revoked_when_reattached(app, auth_client):
    pki = build_cross_pki()
    a_prime = make_cert(pki.name_a, pki.key_a, f'Cross Root C {pki.tag}', new_key(), days=300)
    with app.app_context():
        SmartImporter().execute(pem(a_prime))
        SmartImporter().execute(pem(pki.root_b))
        b = CA.query.filter_by(descr=pki.name_b).one().id
    xid = auth_client.post(_x(b), json={'certificate': pem(pki.cross_b)}).get_json()['data']['id']
    assert auth_client.post(_x(b, xid, '/revoke'), json={}).status_code == 200
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a))
    assert auth_client.delete(_x(b, xid)).status_code in (200, 204)
    assert auth_client.post(_x(b), json={'certificate': pem(pki.cross_b), 'served': True}).status_code == 409
    r = auth_client.post(_x(b), json={'certificate': pem(pki.cross_b)})
    assert r.status_code == 201, r.data
    data = r.get_json()['data']
    assert data['revoked'] is True and data['served'] is False


def test_an_opnsense_import_whose_commit_fails_leaves_nothing_behind(app, auth_client, monkeypatch):
    import base64
    from api.v2 import import_opnsense
    from tests.test_cross_import_opnsense import _row, _Session
    from tests.test_opnsense_import import _key_pem
    pki = build_cross_pki()
    with app.app_context():
        SmartImporter().execute(pem(pki.root_b))
    cross_row = _row(pki.cross_b, 'B cross')
    cross_row['prv'] = base64.b64encode(_key_pem(pki.key_b)).decode()
    rows = [_row(pki.root_a, pki.name_a), cross_row]
    monkeypatch.setattr(import_opnsense, 'create_session', lambda verify_ssl=True: _Session(rows, []))

    def failing_commit(log, message):
        db.session.rollback()
        return False, ({'error': message}, 500)

    monkeypatch.setattr(import_opnsense, 'safe_commit', failing_commit)
    auth_client.post('/api/v2/import/opnsense/import', json={
        'host': 'opnsense.example', 'port': 443, 'api_key': 'k', 'api_secret': 's',
        'verify_ssl': False, 'items': []})
    with app.app_context():
        assert CA.query.filter_by(descr=pki.name_a).count() == 0
        assert CACrossCertificate.query.filter_by(serial_number=str(pki.cross_b.serial_number)).count() == 0
        assert CA.query.filter_by(descr=pki.name_b).one().prv is None
