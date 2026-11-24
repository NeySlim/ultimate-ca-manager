"""SQLite: a CSR signing that meets another writer answers the busy 503 with Retry-After, signs
nothing, logs no error, and the same request signs once the writer is gone.

A second sqlite3 connection really writes, as in tests/test_restore_held_database.py.
"""
import json
import logging
import sqlite3

from models import Certificate, db
from services.trust_store import TrustStoreService
from utils import sqlite_wait
from tests.test_restore_held_database import (  # noqa: F401 (fixture)
    _admin_user, _client, busy_app)


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


def _ca_and_csr(client, count=1):
    ca = _post(client, '/api/v2/cas', {'type': 'root', 'commonName': 'lock-sign Root',
                                       'keyAlgo': 'RSA', 'keySize': 2048, 'validityYears': 5})
    assert ca.status_code in (200, 201), ca.data
    ids = []
    for n in range(count):
        csr = _post(client, '/api/v2/csrs', {'cn': f'lock-sign-{n}.example.test', 'key_type': 'RSA 2048'})
        assert csr.status_code in (200, 201), csr.data
        ids.append(csr.get_json()['data']['id'])
    return ca.get_json()['data']['id'], *ids


def _bulk(csr_ids, ca_id):
    return {'ids': csr_ids, 'ca_id': ca_id, 'validity_days': 30}


def _writer_during_signing(monkeypatch, path):
    """Another connection starts a write while the first certificate is being signed, and ends
    it when the second one is."""
    holder = sqlite3.connect(path, timeout=0, isolation_level=None)
    real = TrustStoreService.sign_csr
    calls = []

    def release():
        if holder.in_transaction:
            holder.execute('ROLLBACK')

    def sign(*args, **kwargs):
        pem = real(*args, **kwargs)
        calls.append(True)
        if len(calls) == 1:
            holder.execute('BEGIN IMMEDIATE')
            holder.execute("UPDATE system_config SET value = value WHERE key = 'none'")
        else:
            release()
        return pem
    monkeypatch.setattr(TrustStoreService, 'sign_csr', staticmethod(sign))
    return holder, release


def test_a_csr_signing_that_meets_a_writer_answers_busy_and_signs_on_retry(busy_app, monkeypatch, caplog):
    app, path = busy_app
    monkeypatch.setattr(sqlite_wait, 'WEB_LOCK_WAIT_SECONDS', 0.3)
    client = _client(app, _admin_user(app)['username'])
    ca_id, csr_id = _ca_and_csr(client)
    holder, release = _writer_during_signing(monkeypatch, path)
    url = f'/api/v2/csrs/{csr_id}/sign'
    try:
        with caplog.at_level(logging.WARNING):
            refused = _post(client, url, {'ca_id': ca_id, 'validity_days': 30})
    finally:
        release()
    assert refused.status_code == 503, refused.data
    assert refused.headers['Retry-After'] == str(sqlite_wait.BUSY_RETRY_AFTER_SECONDS)
    assert refused.get_json()['detail'] == sqlite_wait.BUSY_MESSAGE
    # A lock is the server's load, not a failure of the signing: no error with its traceback
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR and 'CSR Sign Error' in r.getMessage()]
    with app.app_context():
        assert not db.session.get(Certificate, csr_id).crt
    # The writer gone, the same request signs
    try:
        signed = _post(client, url, {'ca_id': ca_id, 'validity_days': 30})
    finally:
        release()
        holder.close()
    assert signed.status_code == 200, signed.data
    with app.app_context():
        assert db.session.get(Certificate, csr_id).crt


def test_a_bulk_signing_that_meets_a_writer_reports_busy_and_signs_the_others(busy_app, monkeypatch, caplog):
    app, path = busy_app
    monkeypatch.setattr(sqlite_wait, 'WEB_LOCK_WAIT_SECONDS', 0.3)
    client = _client(app, _admin_user(app)['username'])
    ca_id, first, second = _ca_and_csr(client, count=2)
    holder, release = _writer_during_signing(monkeypatch, path)
    try:
        with caplog.at_level(logging.WARNING):
            done = _post(client, '/api/v2/csrs/bulk/sign', _bulk([first, second], ca_id))
    finally:
        release()
    # The one that met the lock says the server is busy; the transaction rolled back, the next one signs
    assert done.status_code == 200, done.data
    assert done.get_json()['data']['failed'] == [{'id': first, 'error': sqlite_wait.BUSY_MESSAGE}]
    assert done.get_json()['data']['success'] == [second]
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR and 'Bulk sign: CSR' in r.getMessage()]
    with app.app_context():
        assert not db.session.get(Certificate, first).crt
        assert db.session.get(Certificate, second).crt
    try:
        again = _post(client, '/api/v2/csrs/bulk/sign', _bulk([first], ca_id))
    finally:
        release()
        holder.close()
    assert again.status_code == 200, again.data
    assert again.get_json()['data']['success'] == [first]
