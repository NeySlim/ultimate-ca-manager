"""A revocation writes the certificate row as it stands under its lock, never from the copy
it read before waiting: an unhold or a revocation committed meanwhile is seen and kept."""
import base64
import threading
import uuid

import pytest
from sqlalchemy import delete, select, update

from models import Certificate, RevokedSerial, db
from tests.test_import_issuer_signature import _leaf, _pem, _store
from tests.test_revocation_record_rule import (  # noqa: F401  (issuer is a fixture)
    EARLY, LATER, _held, _on_postgresql, _record, _row, _wait_for_a_lock_waiter, issuer)

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _held_leaf(app, issuer, cn, *, recorded=True):
    _, refid, ca_cert, ca_key = issuer
    real, key = _leaf(cn, ca_cert, ca_key, days=200)
    row_id = _store(app, real, refid, key=key)
    _held(app, row_id)
    record_id = _record(app, refid, real, reason='certificateHold', at=EARLY,
                        certificate_id=row_id) if recorded else None
    return row_id, record_id


def _microsoft_held(app, issuer, cn):
    """A held row with no caref, as a Microsoft CA's certificate is stored: no record exists."""
    _, _, ca_cert, ca_key = issuer
    real, _ = _leaf(cn, ca_cert, ca_key, days=200)
    with app.app_context():
        row = Certificate(refid=str(uuid.uuid4()), descr=cn, caref=None, source='msca',
                          crt=base64.b64encode(_pem(real).encode()).decode(),
                          cert_type='server_cert', subject=real.subject.rfc4514_string(),
                          issuer=real.issuer.rfc4514_string(), serial_number=str(real.serial_number),
                          revoked=True, revoke_reason='certificateHold', revoked_at=EARLY)
        db.session.add(row)
        db.session.commit()
        return row.id


def _unhold_statements(row_id, record_id):
    yield update(Certificate).where(Certificate.id == row_id).values(
        revoked=False, revoke_reason=None, revoked_at=None, invalidity_at=None)
    if record_id is not None:
        yield delete(RevokedSerial).where(RevokedSerial.id == record_id)


def _meanwhile(monkeypatch, statements):
    """Commit ``statements`` on another connection right after the revocation's entry check."""
    from services.cert.mixins import lifecycle
    check, done = lifecycle.revocable, []

    def then_written(*args, **kwargs):
        allowed = check(*args, **kwargs)
        if not done:
            done.append(True)
            with db.engine.begin() as other:
                for statement in statements:
                    other.execute(statement)
        return allowed
    monkeypatch.setattr(lifecycle, 'revocable', then_written)
    return done


def _revoke(app, row_id, reason='keyCompromise'):
    from services.cert_service import CertificateService
    with app.app_context():
        CertificateService.revoke_certificate(row_id, reason=reason, revoke_related=False)


class TestAnUnholdCommittedWhileTheRevocationWaits:

    def test_the_row_ends_revoked(self, app, issuer, monkeypatch):
        row_id, record_id = _held_leaf(app, issuer, 'stale-unhold.example.test')
        done = _meanwhile(monkeypatch, list(_unhold_statements(row_id, record_id)))
        _revoke(app, row_id)
        assert done
        revoked, reason, _ = _row(app, row_id)
        assert (revoked, reason) == (True, 'keyCompromise')
        with app.app_context():
            # Valid when revoked: no invalidity date carried over from the lifted hold
            assert db.session.get(Certificate, row_id).invalidity_at is None

    def test_without_a_ca_record_too(self, app, issuer, monkeypatch):
        row_id = _microsoft_held(app, issuer, 'stale-unhold-msca.example.test')
        done = _meanwhile(monkeypatch, list(_unhold_statements(row_id, None)))
        _revoke(app, row_id)
        assert done
        assert _row(app, row_id)[:2] == (True, 'keyCompromise')


class TestARevocationCommittedWhileTheOtherWaits:

    def test_the_second_one_is_refused_and_the_first_kept(self, app, issuer, monkeypatch):
        row_id, record_id = _held_leaf(app, issuer, 'stale-final.example.test')
        done = _meanwhile(monkeypatch, [
            update(Certificate).where(Certificate.id == row_id).values(
                revoked=True, revoke_reason='superseded', revoked_at=LATER),
            update(RevokedSerial).where(RevokedSerial.id == record_id).values(
                revoke_reason='superseded', revoked_at=LATER)])
        with pytest.raises(ValueError, match='already revoked'):
            _revoke(app, row_id)
        assert done
        assert _row(app, row_id) == (True, 'superseded', LATER)


class TestTwoConnections:
    """PostgreSQL: the unhold holds the record (or the row) while the revocation waits on it."""

    def _race(self, app, row_id, record_id):
        if not _on_postgresql(app):
            pytest.skip('row locks are PostgreSQL behaviour; SQLite serializes writers')
        with app.app_context():
            engine = db.engine
        locked, outcome = threading.Event(), {}

        def unhold():
            try:
                with engine.connect() as conn:
                    with conn.begin():
                        if record_id is not None:
                            conn.execute(select(RevokedSerial.id).where(RevokedSerial.id == record_id)
                                         .with_for_update())
                        else:
                            conn.execute(select(Certificate.id).where(Certificate.id == row_id)
                                         .with_for_update())
                        locked.set()
                        outcome['waited'] = _wait_for_a_lock_waiter(conn)
                        for statement in _unhold_statements(row_id, record_id):
                            conn.execute(statement)
            except Exception as e:  # noqa: BLE001
                outcome['error'] = repr(e)
            finally:
                locked.set()
        worker = threading.Thread(target=unhold)
        worker.start()
        locked.wait(10)
        _revoke(app, row_id)
        worker.join(30)
        assert 'error' not in outcome and outcome.get('waited'), outcome
        assert _row(app, row_id)[:2] == (True, 'keyCompromise')

    def test_with_a_ca_record(self, app, issuer):
        row_id, record_id = _held_leaf(app, issuer, 'race-unhold.example.test')
        self._race(app, row_id, record_id)

    def test_without_a_ca_record(self, app, issuer):
        row_id = _microsoft_held(app, issuer, 'race-unhold-msca.example.test')
        self._race(app, row_id, None)


class TestWhatARefusedOrFailedRevocationLogs:

    def test_an_unexpected_value_error_is_logged(self, app, issuer, monkeypatch, caplog):
        from services.cert.mixins import lifecycle
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('revocation-logs-failure.example.test', ca_cert, ca_key, days=200)
        row_id = _store(app, real, refid, key=key)

        def broken(*_a, **_k):
            raise ValueError('not what a caller expects')
        monkeypatch.setattr(lifecycle, 'remember_if_compromised', broken)
        caplog.set_level('ERROR')
        with pytest.raises(ValueError, match='not what a caller expects'):
            _revoke(app, row_id)
        assert any('not staged' in r.getMessage() for r in caplog.records)
        assert _row(app, row_id)[0] is False

    def test_already_revoked_under_the_lock_is_answered_without_an_error_line(
            self, app, issuer, monkeypatch, caplog):
        row_id, _record_id = _held_leaf(app, issuer, 'revocation-logs-refusal.example.test')
        _meanwhile(monkeypatch, [update(Certificate).where(Certificate.id == row_id).values(
            revoked=True, revoke_reason='superseded', revoked_at=LATER)])
        caplog.set_level('ERROR')
        with pytest.raises(ValueError, match='already revoked'):
            _revoke(app, row_id)
        assert not any('not staged' in r.getMessage() for r in caplog.records)
