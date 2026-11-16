"""A non-zero SSH certificate serial is held once under its CA, and the database says so.

A signature whose serial an older certificate already holds (a counter that trailed its rows)
raises the counter and signs once more; a second refusal answers 409, never 500. A pair the
upgrade marked keeps its oldest holder under the index, and revoking one of a pair revokes all.
"""
import os
import threading
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models import db
from models.ssh import SSHCertificate, SSHCertificateAuthority
from services.ssh_ca_service import SSHCAService
from services.ssh_cert import SSHCertificateService

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
CAS = SSHCertificateAuthority.__table__
WORKERS = 6


def _ca(label):
    return SSHCAService.create_ca(descr=f'{label} {uuid.uuid4().hex[:8]}', ca_type='user', key_type='ed25519',
                                  username='t', allow_any_principal=True).id


def _pubkey():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    return ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()


def _sign(ca_id):
    return SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', ['u']).serial


def _counter(ca_id):
    return db.session.execute(select(CAS.c.serial_counter).where(CAS.c.id == ca_id)).scalar_one()


def _set_counter(ca_id, value):
    db.session.execute(CAS.update().where(CAS.c.id == ca_id).values(serial_counter=value))
    db.session.commit()


def _row(ca_id, serial, marked=False):
    return SSHCertificate(
        refid=str(uuid.uuid4()), ssh_ca_id=ca_id, cert_type='user', key_id='k', public_key='pub',
        certificate='cert', principals='[]', serial=serial, valid_from=datetime(2026, 1, 1),
        valid_to=datetime(2030, 1, 1), key_type='ed25519', fingerprint=f'SHA256:{uuid.uuid4().hex}',
        serial_duplicate=marked)


def _drop(ca_id):
    db.session.rollback()
    SSHCertificate.query.filter_by(ssh_ca_id=ca_id).delete()
    SSHCertificateAuthority.query.filter_by(id=ca_id).delete()
    db.session.commit()


def test_the_database_holds_a_serial_once_per_ca_zero_aside(app):
    with app.app_context():
        ca_id, other = _ca('index'), _ca('index other')
        try:
            db.session.add_all([_row(ca_id, 5), _row(other, 5), _row(ca_id, 0), _row(ca_id, 0)])
            db.session.commit()
            db.session.add(_row(ca_id, 5))
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()
            # A marked row is out of the index; the oldest holder stays in it
            db.session.add(_row(ca_id, 5, marked=True))
            db.session.commit()
        finally:
            _drop(ca_id), _drop(other)


def test_a_signature_behind_a_trailing_counter_raises_it_and_signs(app):
    with app.app_context():
        ca_id = _ca('trailing')
        try:
            assert [_sign(ca_id) for _ in range(3)] == [1, 2, 3]
            _set_counter(ca_id, 1)
            assert _sign(ca_id) == 4
            assert _counter(ca_id) == 4
        finally:
            _drop(ca_id)


def test_a_signature_refused_twice_is_a_conflict(app):
    from services.ssh_cert.signing import SSHSerialConflict
    with app.app_context():
        ca_id = _ca('conflict')
        try:
            _sign(ca_id), _sign(ca_id)
            _set_counter(ca_id, 0)
            with patch.object(SSHCAService, 'raise_serial_counter'), pytest.raises(SSHSerialConflict):
                _sign(ca_id)
            assert SSHCertificate.query.filter_by(ssh_ca_id=ca_id).count() == 2
        finally:
            _drop(ca_id)


def test_another_refusal_is_not_taken_for_a_serial(app):
    """Only the serial index is retried: any other refusal surfaces as it is, one serial spent."""
    with app.app_context():
        ca_id = _ca('other refusal')
        try:
            taken = db.session.get(SSHCertificate, _sign_row(ca_id)).refid
            with patch('services.ssh_cert.signing.uuid.uuid4', return_value=taken), \
                    pytest.raises(IntegrityError):
                _sign(ca_id)
            assert _counter(ca_id) == 2
        finally:
            _drop(ca_id)


def _sign_row(ca_id):
    return SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', ['u']).id


@pytest.mark.parametrize('route, body', [
    ('/api/v2/ssh/certificates', {'public_key': 'KEY'}),
    ('/api/v2/ssh/certificates/generate', {'key_type': 'ed25519'}),
])
def test_the_api_answers_409_when_the_serial_stays_taken(app, auth_client, route, body):
    with app.app_context():
        ca_id = _ca('api conflict')
        _sign(ca_id), _sign(ca_id)
        _set_counter(ca_id, 0)
    try:
        payload = {'ca_id': ca_id, 'cert_type': 'user', 'principals': ['u'],
                   **{k: (_pubkey() if v == 'KEY' else v) for k, v in body.items()}}
        with patch.object(SSHCAService, 'raise_serial_counter'):
            response = auth_client.post(route, json=payload)
        assert response.status_code == 409, response.get_json()
        assert 'already held' in response.get_json()['message']
    finally:
        with app.app_context():
            _drop(ca_id)


# --- signatures together behind a trailing counter ------------------------------------------

def _sign_together(app, ca_id):
    errors, serials, ready = [], [], threading.Barrier(WORKERS)
    real = SSHCAService.get_private_key_object

    def wait_for_the_others(cid):
        try:
            ready.wait(10)
        except threading.BrokenBarrierError:
            pass
        return real(cid)

    def worker(n):
        try:
            with app.app_context():
                serials.append(SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', [f'w{n}']).serial)
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    with patch.object(SSHCAService, 'get_private_key_object', side_effect=wait_for_the_others):
        threads = [threading.Thread(target=worker, args=(n,)) for n in range(WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
    return errors, serials


def _together_behind_a_trailing_counter(app):
    with app.app_context():
        ca_id = _ca('race')
        held = [_sign(ca_id) for _ in range(3)]
        _set_counter(ca_id, 0)
        db.session.remove()
    errors, serials = _sign_together(app, ca_id)
    with app.app_context():
        stored = sorted(s for (s,) in db.session.query(SSHCertificate.serial).filter_by(ssh_ca_id=ca_id))
        db.session.remove()
    assert errors == []
    assert len(set(serials)) == WORKERS and not set(serials) & set(held)
    assert stored == sorted(held + serials)


def test_signatures_together_behind_a_trailing_counter_on_sqlite(app, tmp_path):
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'ssh-unique.db'}"):
        _together_behind_a_trailing_counter(app)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_signatures_together_behind_a_trailing_counter_on_postgresql(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'ssh_unique_race_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        _together_behind_a_trailing_counter(app)
