"""Garde de suppression des certificats SSH valides."""
from datetime import timedelta

from models import db
from models.ssh import SSHCertificate
from utils.datetime_utils import utc_now
from tests.test_ssh import _create_ssh_ca, _generate_test_ssh_key, post_json

MSG = 'Cannot delete a valid, non-revoked SSH certificate. Revoke it first.'


def _issue(auth_client):
    ca = _create_ssh_ca(auth_client, descr='Guard CA')
    r = post_json(auth_client, '/api/v2/ssh/certificates', {
        'ca_id': ca['id'], 'public_key': _generate_test_ssh_key(),
        'cert_type': 'user', 'principals': ['guard'],
    })
    assert r.status_code == 201
    return r.get_json()['data']['id']


def _exists(app, cid):
    with app.app_context():
        return db.session.get(SSHCertificate, cid) is not None


def test_valid_certificate_refused(app, auth_client):
    cid = _issue(auth_client)
    r = auth_client.delete(f'/api/v2/ssh/certificates/{cid}')
    assert r.status_code == 409
    assert r.get_json()['message'] == MSG
    assert _exists(app, cid)


def test_revoked_certificate_deleted(app, auth_client):
    cid = _issue(auth_client)
    post_json(auth_client, f'/api/v2/ssh/certificates/{cid}/revoke', {'reason': 'unspecified'})
    assert auth_client.delete(f'/api/v2/ssh/certificates/{cid}').status_code == 204
    assert not _exists(app, cid)


def test_expired_certificate_deleted(app, auth_client):
    cid = _issue(auth_client)
    with app.app_context():
        c = db.session.get(SSHCertificate, cid)
        c.valid_to = utc_now() - timedelta(days=1)
        db.session.commit()
    assert auth_client.delete(f'/api/v2/ssh/certificates/{cid}').status_code == 204
    assert not _exists(app, cid)


def test_unknown_certificate_404(auth_client):
    assert auth_client.delete('/api/v2/ssh/certificates/999999').status_code == 404


def test_refusal_writes_no_audit(app, auth_client):
    from models import AuditLog

    def count():
        with app.app_context():
            return AuditLog.query.filter_by(action='ssh_cert_deleted').count()

    cid = _issue(auth_client)
    before = count()
    assert auth_client.delete(f'/api/v2/ssh/certificates/{cid}').status_code == 409
    assert count() == before
