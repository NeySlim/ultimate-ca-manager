"""An empty private key column means "no key": it is neither counted as an
unencrypted key nor reported as encrypted by encrypt-all-keys."""
import uuid

from models import db, Certificate


def _status(client):
    response = client.get('/api/v2/system/security/encryption-status')
    assert response.status_code == 200, response.data
    return response.get_json()['data']


def _dry_run(client):
    # A dry run only: a real run would encrypt the shared test database's keys
    response = client.post('/api/v2/system/security/encrypt-all-keys',
                           json={'dry_run': True})
    assert response.status_code == 200, response.data
    return response.get_json()['data']


def test_an_empty_key_is_not_counted(app, auth_client, encryption_enabled):
    before_status, before_run = _status(auth_client), _dry_run(auth_client)
    with app.app_context():
        row = Certificate(refid=str(uuid.uuid4()), descr='empty key', crt='', prv='')
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    try:
        status, run = _status(auth_client), _dry_run(auth_client)
        assert status['unencrypted_count'] == before_status['unencrypted_count']
        assert status['total_keys'] == before_status['total_keys']
        assert run['encrypted'] == before_run['encrypted']
        assert run['skipped'] == before_run['skipped']
    finally:
        with app.app_context():
            db.session.delete(db.session.get(Certificate, row_id))
            db.session.commit()
