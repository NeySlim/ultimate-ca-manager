"""A CA whose stored key is not its certificate's key signs no CRL, whoever asks:
the scheduler, the manual route or a restore."""
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from models import CA, Certificate, db
from models.crl import CRLMetadata


@pytest.fixture
def mismatched(app, create_ca):
    """A publishing CA whose key column holds a stranger's key; removed with its rows."""
    from utils.key_codec import store_pem_bytes
    created = create_ca(cn='CRL Mismatched Key')
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    with app.app_context():
        row = db.session.get(CA, created['id'])
        row.cdp_enabled = True
        row.prv = store_pem_bytes(stranger)
        db.session.commit()
    yield created['id']
    with app.app_context():
        db.session.rollback()
        row = db.session.get(CA, created['id'])
        CRLMetadata.query.filter_by(ca_id=created['id']).delete(synchronize_session=False)
        Certificate.query.filter_by(caref=row.refid).delete(synchronize_session=False)
        db.session.flush()
        CA.query.filter_by(id=created['id']).delete(synchronize_session=False)
        db.session.commit()


def _count(ca_id):
    return CRLMetadata.query.filter_by(ca_id=ca_id).count()


def test_the_scheduler_signs_no_crl_with_another_key(app, mismatched, caplog):
    from services.crl_scheduler_task import CRLSchedulerTask
    with app.app_context():
        before = _count(mismatched)
        assert CRLSchedulerTask.regenerate_crl(mismatched) is False
        assert _count(mismatched) == before
    assert any('not the key of its certificate' in r.getMessage() for r in caplog.records)


def test_the_manual_route_says_why_no_crl_was_signed(app, auth_client, mismatched):
    r = auth_client.post(f'/api/v2/crl/{mismatched}/regenerate')
    assert r.status_code == 409, r.get_json()
    assert 'not the key of its certificate' in r.get_json()['message']
    with app.app_context():
        assert _count(mismatched) == 0


def test_the_manual_delta_route_says_why_no_crl_was_signed(app, auth_client, mismatched):
    with app.app_context():
        db.session.get(CA, mismatched).delta_crl_enabled = True
        db.session.commit()
    r = auth_client.post(f'/api/v2/crl/{mismatched}/delta/regenerate')
    assert r.status_code == 409, r.get_json()
    assert 'not the key of its certificate' in r.get_json()['message']


def test_a_matching_key_still_signs(app, create_ca):
    from services.crl_service import CRLService
    created = create_ca(cn='CRL Matching Key')
    try:
        with app.app_context():
            assert CRLService.generate_crl(created['id']).crl_der
    finally:
        with app.app_context():
            refid = db.session.get(CA, created['id']).refid
            CRLMetadata.query.filter_by(ca_id=created['id']).delete(synchronize_session=False)
            Certificate.query.filter_by(caref=refid).delete(synchronize_session=False)
            db.session.flush()
            CA.query.filter_by(id=created['id']).delete(synchronize_session=False)
            db.session.commit()
