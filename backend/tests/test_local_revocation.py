"""Revocations UCM publishes and revocations it only records (issue #450).

Under a CA whose key UCM does not hold, nothing relying parties read ever carries a revocation:
a valid certificate is deleted without one, each record says at its write whether it was
published, and a local revocation is lifted by an administrator, for good (no repair brings it
back). A published revocation is never lifted, except a hold through Unhold.
"""
import base64
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from models import CA, Certificate, RevokedSerial, SystemConfig, db
from models.audit_log import AuditLog
from tests.test_import_issuer_signature import _leaf, _store
from tests.test_revocation_record_rule import (  # noqa: F401  (issuer is a fixture)
    _on_postgresql, _record, _row, _wait_for_a_lock_waiter, issuer)

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates', 'drop_new_config_rows')

LIFT = '/api/v2/certificates/{}/lift-local-revocation'
# An archive older than upgrade step 176 carries no `published` key
_DROP = object()


def _post(client, url, body=None):
    return client.post(url, data=json.dumps(body if body is not None else {}),
                       content_type='application/json')


@pytest.fixture(scope='module')
def keyless(app, create_ca):
    """(id, refid, certificate, signing key) of a CA held without its key, as an imported
    public CA: the key signs the test's leaves, UCM never sees it."""
    data = create_ca(cn=f'Keyless 450 CA {uuid.uuid4().hex[:6]}',
                     keyUsage=['digitalSignature', 'keyCertSign', 'cRLSign'])
    with app.app_context():
        from services.hsm.ca_key_loader import get_ca_signing_key
        row = db.session.get(CA, data['id'])
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        key = get_ca_signing_key(row)
        row.prv = None
        db.session.commit()
        return row.id, row.refid, cert, key


@pytest.fixture
def ca_state(app, keyless):
    """Sets the keyless CA's state for one test, put back after it."""
    def put(**fields):
        with app.app_context():
            ca = db.session.get(CA, keyless[0])
            for name, value in fields.items():
                setattr(ca, name, value)
            db.session.commit()
    yield put
    put(offline=False, offline_mode=None)
    with app.app_context():
        SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{keyless[0]}').delete()
        db.session.commit()


def _leaf_row(app, issuer, cn):
    _, refid, ca_cert, ca_key = issuer
    real, key = _leaf(f'{cn}-{uuid.uuid4().hex[:6]}.example.test', ca_cert, ca_key, days=200)
    return _store(app, real, refid, key=key), real


def _records(app, refid, real):
    with app.app_context():
        return [(r.revoke_reason, r.published) for r in RevokedSerial.query.filter_by(
            caref=refid, serial_number=str(real.serial_number)).order_by(RevokedSerial.id)]


def _revoke(client, row_id, reason='superseded'):
    r = _post(client, f'/api/v2/certificates/{row_id}/revoke', {'reason': reason})
    assert r.status_code == 200, r.data
    return r


def _detail(client, row_id):
    r = client.get(f'/api/v2/certificates/{row_id}')
    assert r.status_code == 200, r.data
    return r.get_json()['data']


def _responder(app, ca_id, issuer):
    """A delegated OCSP responder configured for ``ca_id``, its key held by UCM."""
    row_id, _ = _leaf_row(app, issuer, 'responder')
    with app.app_context():
        db.session.add(SystemConfig(key=f'ocsp_responder_cert_{ca_id}', value=str(row_id)))
        db.session.commit()
    return row_id


def _exists(app, row_id):
    with app.app_context():
        return db.session.get(Certificate, row_id) is not None


class TestDeletionWithoutRevocation:
    def test_a_valid_certificate_of_a_keyless_ca_is_deleted_by_both_routes(
            self, app, auth_client, keyless):
        unit, real = _leaf_row(app, keyless, 'unit-delete')
        assert auth_client.delete(f'/api/v2/certificates/{unit}').status_code == 204
        assert not _exists(app, unit) and _records(app, keyless[1], real) == []
        bulk, _ = _leaf_row(app, keyless, 'bulk-delete')
        r = _post(auth_client, '/api/v2/certificates/bulk/delete', {'ids': [bulk]})
        assert r.get_json()['data']['failed'] == [], r.data
        assert not _exists(app, bulk)

    def test_a_valid_certificate_linked_to_no_ca_is_deleted(self, app, auth_client, keyless):
        _, _, ca_cert, ca_key = keyless
        real, key = _leaf(f'unlinked-{uuid.uuid4().hex[:6]}.example.test', ca_cert, ca_key, days=200)
        row_id = _store(app, real, None, key=key)
        assert auth_client.delete(f'/api/v2/certificates/{row_id}').status_code == 204

    def test_a_ca_holding_its_key_still_refuses_both_routes(self, app, auth_client, issuer):
        row_id, _ = _leaf_row(app, issuer, 'keyed-delete')
        r = auth_client.delete(f'/api/v2/certificates/{row_id}')
        assert r.status_code == 409 and b'revoke it first' in r.data
        bulk = _post(auth_client, '/api/v2/certificates/bulk/delete', {'ids': [row_id]})
        assert bulk.get_json()['data']['failed'][0]['id'] == row_id
        assert _exists(app, row_id)

    @pytest.mark.parametrize('state', ['offline', 'responder'])
    def test_an_offline_ca_or_a_delegated_responder_keeps_the_refusal(
            self, app, auth_client, keyless, issuer, ca_state, state):
        if state == 'offline':
            ca_state(offline=True, offline_mode='file_exported')
        else:
            _responder(app, keyless[0], issuer)
        row_id, _ = _leaf_row(app, keyless, f'{state}-delete')
        assert auth_client.delete(f'/api/v2/certificates/{row_id}').status_code == 409
        assert _detail(auth_client, row_id)['revocation_published'] is True

    def test_a_copy_revoked_by_its_serials_record_only_is_deletable(self, app, auth_client, issuer):
        # A certificate revoked, deleted and stored again before the hourly repair marks the copy
        row_id, real = _leaf_row(app, issuer, 'record-only')
        _record(app, issuer[1], real, reason='superseded', certificate_id=row_id)
        assert _row(app, row_id)[0] is False
        assert auth_client.delete(f'/api/v2/certificates/{row_id}').status_code == 204


class TestEveryRecordSaysWhetherItWasPublished:
    def test_under_a_ca_holding_its_key_the_record_is_published(self, app, auth_client, issuer):
        row_id, real = _leaf_row(app, issuer, 'published')
        _revoke(auth_client, row_id)
        assert _records(app, issuer[1], real) == [('superseded', True)]

    def test_under_a_keyless_ca_the_record_is_local(self, app, auth_client, keyless):
        row_id, real = _leaf_row(app, keyless, 'local')
        _revoke(auth_client, row_id)
        assert _records(app, keyless[1], real) == [('superseded', False)]

    @pytest.mark.parametrize('state', ['offline', 'responder'])
    def test_an_offline_ca_or_a_delegated_responder_publishes(
            self, app, auth_client, keyless, issuer, ca_state, state):
        if state == 'offline':
            ca_state(offline=True, offline_mode='file_exported')
        else:
            _responder(app, keyless[0], issuer)
        row_id, real = _leaf_row(app, keyless, f'{state}-write')
        _revoke(auth_client, row_id)
        assert _records(app, keyless[1], real) == [('superseded', True)]

    def test_a_record_published_once_stays_published_and_unknown_stays_unknown(self, app, keyless, issuer):
        from services.cert.local_revocation import note_publication
        with app.app_context():
            keyless_ca, keyed_ca = db.session.get(CA, keyless[0]), db.session.get(CA, issuer[0])
            for before, ca, fresh, after in ((None, keyless_ca, True, False), (None, keyless_ca, False, None),
                                             (True, keyless_ca, False, True), (False, keyed_ca, False, True),
                                             (None, keyed_ca, False, True), (False, keyless_ca, False, False)):
                record = RevokedSerial(published=before)
                note_publication(record, ca, fresh)
                assert record.published is after, (before, ca.id, fresh)

    def test_the_superseded_record_of_a_renewal_says_it_too(self, app, keyless):
        from services.cert.renewal import _record_superseded
        from utils.datetime_utils import utc_now
        row_id, real = _leaf_row(app, keyless, 'superseded')
        with app.app_context():
            _record_superseded(row_id, db.session.get(CA, keyless[0]), str(real.serial_number),
                               real.not_valid_after_utc.replace(tzinfo=None), utc_now())
            db.session.commit()
        assert _records(app, keyless[1], real) == [('superseded', False)]


class TestLiftingALocalRevocation:
    def test_the_detail_says_what_may_be_lifted(self, app, auth_client, keyless, issuer):
        local, _ = _leaf_row(app, keyless, 'detail-local')
        keyed, _ = _leaf_row(app, issuer, 'detail-keyed')
        assert _detail(auth_client, local)['revocation_published'] is False
        assert _detail(auth_client, local)['local_revocation_lift'] is None
        for row_id in (local, keyed):
            _revoke(auth_client, row_id)
        assert _detail(auth_client, local)['local_revocation_lift'] == 'local'
        assert _detail(auth_client, keyed)['local_revocation_lift'] is None
        assert _detail(auth_client, keyed)['revocation_published'] is True

    def test_a_lift_is_confirmed_audited_and_final(self, app, auth_client, keyless):
        from services.cert.issued_lookup import apply_persisted_revocation, apply_persisted_revocations
        row_id, real = _leaf_row(app, keyless, 'lift')
        _revoke(auth_client, row_id, 'keyCompromise')
        unconfirmed = _post(auth_client, LIFT.format(row_id))
        assert unconfirmed.status_code == 400 and _row(app, row_id)[0] is True
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        assert r.status_code == 200, r.data
        assert r.get_json()['data']['revoked'] is False
        assert _row(app, row_id) == (False, None, None)
        assert _records(app, keyless[1], real) == []
        with app.app_context():
            assert AuditLog.query.filter_by(action='certificate_local_revocation_lifted',
                                            resource_id=str(row_id)).count() == 1
            # The hourly repair finds nothing to mark, and a copy stored again comes back valid
            assert apply_persisted_revocations({row_id}) == []
            db.session.rollback()
        assert auth_client.delete(f'/api/v2/certificates/{row_id}').status_code == 204
        again = _store(app, real, keyless[1])
        with app.app_context():
            assert apply_persisted_revocation(db.session.get(Certificate, again)) is False
        assert _row(app, again)[0] is False

    def test_an_operator_cannot_lift(self, app, auth_client, keyless, create_user):
        user = create_user(username='op_local_lift', role='operator')
        try:
            operator = app.test_client()
            assert _post(operator, '/api/v2/auth/login', {'username': 'op_local_lift',
                                                          'password': 'TestPass123!'}).status_code == 200
            row_id, _ = _leaf_row(app, keyless, 'operator')
            _revoke(auth_client, row_id)
            assert _post(operator, LIFT.format(row_id), {'confirm': True}).status_code == 403
            assert _row(app, row_id)[0] is True
        finally:
            auth_client.delete(f"/api/v2/users/{user['id']}")

    def test_a_published_revocation_is_refused_with_a_readable_409(self, app, auth_client, issuer):
        row_id, real = _leaf_row(app, issuer, 'refused')
        _revoke(auth_client, row_id)
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True, 'acknowledge_unknown_publication': True})
        assert r.status_code == 409 and 'published' in r.get_json()['message']
        assert _row(app, row_id)[0] is True and _records(app, issuer[1], real) == [('superseded', True)]

    def test_a_published_hold_points_at_unhold(self, app, auth_client, issuer):
        row_id, _ = _leaf_row(app, issuer, 'held')
        _revoke(auth_client, row_id, 'certificateHold')
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        assert r.status_code == 409 and 'Unhold' in r.get_json()['message']

    def test_a_record_published_before_the_ca_lost_its_key_stays(self, app, auth_client, keyless):
        row_id, real = _leaf_row(app, keyless, 'was-published')
        _record(app, keyless[1], real, reason='superseded', certificate_id=row_id)
        with app.app_context():
            RevokedSerial.query.filter_by(certificate_id=row_id).update({'published': True})
            db.session.commit()
        assert _detail(auth_client, row_id)['local_revocation_lift'] is None
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        assert r.status_code == 409 and 'this revocation was published' in r.get_json()['message']
        assert 'signs CRLs' not in r.get_json()['message']
        assert _records(app, keyless[1], real) == [('superseded', True)]

    def test_a_ca_that_publishes_now_refuses_a_local_record(self, app, auth_client, keyless, issuer, ca_state):
        row_id, real = _leaf_row(app, keyless, 'publishes-now')
        _revoke(auth_client, row_id)
        _responder(app, keyless[0], issuer)
        assert _post(auth_client, LIFT.format(row_id), {'confirm': True}).status_code == 409
        # The responder answers for it from now on: published
        assert _records(app, keyless[1], real) == [('superseded', True)]

    def test_an_existing_record_of_unknown_publication_needs_the_risk_acknowledged(
            self, app, auth_client, keyless):
        row_id, real = _leaf_row(app, keyless, 'unknown')
        _record(app, keyless[1], real, reason='superseded', certificate_id=row_id)
        assert _records(app, keyless[1], real) == [('superseded', None)]
        assert _detail(auth_client, row_id)['local_revocation_lift'] == 'unknown'
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        assert r.status_code == 409 and 'may have been published' in r.get_json()['message']
        assert _records(app, keyless[1], real) == [('superseded', None)]
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True, 'acknowledge_unknown_publication': True})
        assert r.status_code == 200, r.data
        assert _records(app, keyless[1], real) == []

    def test_a_row_revoked_without_a_record_is_never_lifted(self, app, auth_client, keyless):
        # Its records may have gone with a deleted CA of the same key, which published them
        row_id, _ = _leaf_row(app, keyless, 'row-only')
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            row.revoked, row.revoke_reason = True, 'superseded'
            db.session.commit()
        assert _detail(auth_client, row_id)['local_revocation_lift'] is None
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True, 'acknowledge_unknown_publication': True})
        assert r.status_code == 409 and 'no record' in r.get_json()['message'], r.data
        assert _row(app, row_id)[0] is True

    def test_an_unrevoked_certificate_has_nothing_to_lift(self, app, auth_client, keyless):
        row_id, _ = _leaf_row(app, keyless, 'valid')
        assert _post(auth_client, LIFT.format(row_id), {'confirm': True}).status_code == 400

    def test_a_record_changed_while_the_lift_runs_refuses_it(self, app, auth_client, keyless, monkeypatch):
        """Seen under the second lock (taken after the rows): a revocation written meanwhile stays."""
        from services.cert import issued_lookup
        row_id, real = _leaf_row(app, keyless, 'meanwhile')
        _revoke(auth_client, row_id)
        lock, calls = issued_lookup.lock_serial_records, []

        def lock_then_revoke_meanwhile(targets):
            calls.append(1)
            if len(calls) == 2:
                db.session.add(RevokedSerial(caref=keyless[1], serial_number=str(real.serial_number),
                                             revoke_reason='keyCompromise',
                                             valid_to=real.not_valid_after_utc.replace(tzinfo=None)))
                db.session.flush()
            return lock(targets)
        monkeypatch.setattr(issued_lookup, 'lock_serial_records', lock_then_revoke_meanwhile)
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        assert r.status_code == 409 and 'meanwhile' in r.get_json()['message'], r.data
        assert len(calls) == 2
        assert _row(app, row_id)[0] is True and _records(app, keyless[1], real) == [('superseded', False)]

    def test_a_lift_during_the_hourly_pass_ends_lifted(self, app, auth_client, keyless, monkeypatch):
        """PostgreSQL: the pass marks the row under its share lock on the record; the lift waits
        for it, then clears the row and deletes the record, and the next pass marks nothing."""
        from services.cert import issued_lookup
        if not _on_postgresql(app):
            pytest.skip('row locks are PostgreSQL behaviour; SQLite serializes writers')
        row_id, real = _leaf_row(app, keyless, 'pass')
        _record(app, keyless[1], real, reason='superseded', certificate_id=row_id)
        with app.app_context():
            RevokedSerial.query.filter_by(certificate_id=row_id).update({'published': False})
            db.session.commit()
            engine = db.engine
        paused, release, outcome = threading.Event(), threading.Event(), {}
        mark = issued_lookup._mark_while_recorded

        def pause_after_the_mark(row, record):
            done = mark(row, record)
            if threading.current_thread().name == 'pass':
                paused.set()
                release.wait(30)
            return done
        monkeypatch.setattr(issued_lookup, '_mark_while_recorded', pause_after_the_mark)

        def hourly_pass():
            with app.app_context():
                try:
                    outcome['marked'] = len(issued_lookup.apply_persisted_revocations({row_id}))
                    db.session.commit()
                except Exception as e:  # noqa: BLE001
                    db.session.rollback()
                    outcome['pass'] = repr(e)
                finally:
                    paused.set()
                    db.session.remove()

        def release_once_the_lift_waits():
            with engine.connect() as conn:
                outcome['waited'] = _wait_for_a_lock_waiter(conn, 10)
            release.set()

        worker = threading.Thread(target=hourly_pass, name='pass')
        worker.start()
        assert paused.wait(30)
        releaser = threading.Thread(target=release_once_the_lift_waits)
        releaser.start()
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        worker.join(30)
        releaser.join(30)
        assert 'pass' not in outcome and outcome.get('waited') and outcome.get('marked') == 1, outcome
        assert r.status_code == 200, r.data
        assert _row(app, row_id)[0] is False and _records(app, keyless[1], real) == []
        with app.app_context():
            assert issued_lookup.apply_persisted_revocations({row_id}) == []
            db.session.rollback()


    def test_a_lift_meeting_a_locked_copy_refuses_at_once(self, app, auth_client, keyless):
        """PostgreSQL: a renewal or the SKI/AKI merge holds a copy's row, then asks for the CA
        rows the lift holds: the lift never waits on a row (no deadlock), it refuses."""
        if not _on_postgresql(app):
            pytest.skip('row locks are PostgreSQL behaviour; SQLite serializes writers')
        row_id, _ = _leaf_row(app, keyless, 'row-held')
        _revoke(auth_client, row_id)
        with app.app_context():
            engine = db.engine
        holding, release, outcome = threading.Event(), threading.Event(), {}

        def hold_the_row():
            with app.app_context():
                try:
                    db.session.query(Certificate.id).filter(Certificate.id == row_id).with_for_update().first()
                    holding.set()
                    release.wait(30)
                finally:
                    holding.set()
                    db.session.rollback()
                    db.session.remove()

        def release_once_the_lift_waits():
            with engine.connect() as conn:
                outcome['waited'] = _wait_for_a_lock_waiter(conn, 3)
            release.set()

        holder = threading.Thread(target=hold_the_row)
        holder.start()
        assert holding.wait(30)
        releaser = threading.Thread(target=release_once_the_lift_waits)
        releaser.start()
        try:
            r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        finally:
            release.set()
            holder.join(30)
            releaser.join(30)
        assert r.status_code == 409 and 'try again' in r.get_json()['message'], r.data
        assert not outcome.get('waited') and _row(app, row_id)[0] is True


    def test_a_revocation_holding_its_record_and_a_lift_do_not_deadlock(
            self, app, auth_client, keyless, monkeypatch):
        """PostgreSQL: a revocation holds the record and the row, then share locks the CA rows the
        lift share locked before waiting on that record: both share, so neither waits for the other."""
        from services.cert import local_revocation
        from services.cert_service import CertificateService
        if not _on_postgresql(app):
            pytest.skip('row locks are PostgreSQL behaviour; SQLite serializes writers')
        row_id, real = _leaf_row(app, keyless, 'hold-then-final')
        _revoke(auth_client, row_id, 'certificateHold')
        with app.app_context():
            engine = db.engine
        holds, lift_waits, outcome = threading.Event(), threading.Event(), {}
        hold = local_revocation._hold_issuer

        def pause_holding_the_record(ca):
            if threading.current_thread().name == 'revocation':
                holds.set()
                lift_waits.wait(30)
            return hold(ca)
        monkeypatch.setattr(local_revocation, '_hold_issuer', pause_holding_the_record)

        def revoke_for_good():
            with app.app_context():
                try:
                    CertificateService.revoke_certificate(row_id, 'keyCompromise', username='admin')
                except Exception as e:  # noqa: BLE001
                    outcome['revocation'] = repr(e)
                finally:
                    holds.set()
                    db.session.remove()

        def go_on_once_the_lift_waits():
            with engine.connect() as conn:
                outcome['waited'] = _wait_for_a_lock_waiter(conn, 10)
            lift_waits.set()

        revocation = threading.Thread(target=revoke_for_good, name='revocation')
        revocation.start()
        assert holds.wait(30)
        releaser = threading.Thread(target=go_on_once_the_lift_waits)
        releaser.start()
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        revocation.join(30)
        releaser.join(30)
        assert 'revocation' not in outcome and outcome.get('waited'), outcome
        assert r.status_code in (200, 409), r.data


class TestTheNoteTravelsInBackups:
    """A restore writes the archive's note, and a merge never turns a published record local."""

    def _archive_row(self, app, refid, real, **changes):
        from services.backup.export_generic import IdentityIndex, export_section
        with app.app_context():
            rows = [r for r in export_section('revoked_serials', IdentityIndex())
                    if r['caref'] == refid and r['serial_number'] == str(real.serial_number)]
        assert len(rows) == 1
        row = dict(rows[0], **changes)
        return {k: v for k, v in row.items() if v is not _DROP}

    def _restore(self, app, row, merging):
        from services.backup.backup_service import BackupService
        with app.app_context():
            service = BackupService()
            service._merging = merging
            service._restore_revoked_serials({'revoked_serials': [row]}, {})
            db.session.commit()

    @pytest.mark.parametrize('archived, merging, here, after', [
        (False, False, None, False), (True, False, None, True), (_DROP, False, None, None),
        (True, True, False, True), (False, True, True, True), (_DROP, True, False, None),
        (False, True, False, False),
    ])
    def test_the_note_is_restored(self, app, keyless, archived, merging, here, after):
        row_id, real = _leaf_row(app, keyless, 'restore')
        _record(app, keyless[1], real, reason='superseded', certificate_id=row_id)
        row = self._archive_row(app, keyless[1], real, published=archived)
        with app.app_context():
            query = RevokedSerial.query.filter_by(caref=keyless[1], serial_number=str(real.serial_number))
            if here is None:
                query.delete()
            else:
                query.update({'published': here})
            db.session.commit()
        self._restore(app, row, merging)
        assert _records(app, keyless[1], real) == [('superseded', after)]


def _keyless_ca(app, create_ca, name):
    """A CA of its own held without its key, for a test that changes what it publishes."""
    data = create_ca(cn=f'{name} {uuid.uuid4().hex[:6]}',
                     keyUsage=['digitalSignature', 'keyCertSign', 'cRLSign'])
    with app.app_context():
        from services.hsm.ca_key_loader import get_ca_signing_key
        row = db.session.get(CA, data['id'])
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        key = get_ca_signing_key(row)
        row.prv = None
        db.session.commit()
        return row.id, row.refid, cert, key


def _key_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _stored_key(key):
    from security.encryption import encrypt_private_key
    return encrypt_private_key(base64.b64encode(_key_pem(key)).decode())


def _external_crl(ca_cert, ca_key, serials, number=1):
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateRevocationListBuilder().issuer_name(ca_cert.subject)
               .last_update(now - timedelta(minutes=1)).next_update(now + timedelta(days=7))
               .add_extension(x509.CRLNumber(number), critical=False))
    for serial in serials:
        builder = builder.add_revoked_certificate(
            x509.RevokedCertificateBuilder().serial_number(serial)
            .revocation_date(now - timedelta(minutes=2)).build())
    return builder.sign(ca_key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)


def _install_crl(auth_client, ca_id, pem):
    r = auth_client.post(f'/api/v2/cas/{ca_id}/crl', json={'pem_content': pem.decode()})
    assert r.status_code in (200, 201), r.data


def _drop_key(app, ca_id):
    with app.app_context():
        db.session.get(CA, ca_id).prv = None
        db.session.commit()


class TestAnExternalCrlPublishesWhatItLists:
    """An external CRL UCM serves for a CA held without its key carries what it lists, and only
    that: UCM signs nothing for that CA, so a revocation the CRL does not list is local."""

    def test_a_revocation_the_external_crl_lists_is_never_lifted(self, app, auth_client, create_ca):
        from services.crl.external import ExternalCRLMixin
        ca = _keyless_ca(app, create_ca, 'External CRL 450')
        row_id, real = _leaf_row(app, ca, 'listed')
        _revoke(auth_client, row_id, 'keyCompromise')
        assert _records(app, ca[1], real) == [('keyCompromise', False)]
        _install_crl(auth_client, ca[0], _external_crl(ca[2], ca[3], [real.serial_number]))
        assert _records(app, ca[1], real) == [('keyCompromise', True)]
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True, 'acknowledge_unknown_publication': True})
        assert r.status_code == 409, r.data
        assert _row(app, row_id)[0] is True
        with app.app_context():
            assert ExternalCRLMixin.get_external_revocation(ca[0], real.serial_number) is not None

    def test_what_the_external_crl_does_not_list_is_local(self, app, auth_client, create_ca):
        ca = _keyless_ca(app, create_ca, 'External CRL 450 unlisted')
        row_id, real = _leaf_row(app, ca, 'unlisted')
        _revoke(auth_client, row_id)
        valid, _ = _leaf_row(app, ca, 'unlisted-valid')
        listed, listed_real = _leaf_row(app, ca, 'listed-valid')
        _install_crl(auth_client, ca[0], _external_crl(ca[2], ca[3], [listed_real.serial_number]))
        assert _records(app, ca[1], real) == [('superseded', False)]
        assert _detail(auth_client, row_id)['local_revocation_lift'] == 'local'
        assert _detail(auth_client, valid)['revocation_published'] is False
        # Listed by the CRL relying parties read, though valid here: revoked first
        assert _detail(auth_client, listed)['revocation_published'] is True
        assert auth_client.delete(f'/api/v2/certificates/{listed}').status_code == 409
        assert auth_client.delete(f'/api/v2/certificates/{valid}').status_code == 204
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        assert r.status_code == 200, r.data
        assert _records(app, ca[1], real) == []

    def test_the_lift_asks_the_served_crl_itself(self, app, auth_client, create_ca):
        """Whatever the records say, a serial the served CRL lists stays revoked."""
        ca = _keyless_ca(app, create_ca, 'External CRL 450 served')
        row_id, real = _leaf_row(app, ca, 'served')
        _revoke(auth_client, row_id)
        _install_crl(auth_client, ca[0], _external_crl(ca[2], ca[3], [real.serial_number]))
        with app.app_context():
            RevokedSerial.query.filter_by(caref=ca[1]).update({'published': False})
            db.session.commit()
        assert _detail(auth_client, row_id)['local_revocation_lift'] is None
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        assert r.status_code == 409 and 'external CRL' in r.get_json()['message'], r.data
        assert _row(app, row_id)[0] is True


def _signed_crl(app, ca_id, this_update, external=False):
    """A CRL row of ``ca_id`` as UCM stores one it signed (or an external upload), dated ``this_update``."""
    from sqlalchemy import func
    from models.crl import CRLMetadata
    with app.app_context():
        number = (db.session.query(func.max(CRLMetadata.crl_number)).filter_by(ca_id=ca_id).scalar() or 0) + 1
        row = CRLMetadata(ca_id=ca_id, crl_number=number, this_update=this_update,
                          next_update=this_update + timedelta(days=7), crl_pem='-', crl_der=b'-',
                          is_external=bool(external))
        db.session.add(row)
        db.session.flush()
        if external is None:  # a row older than the column: NULL, not its default
            CRLMetadata.query.filter_by(id=row.id).update({'is_external': None})
        db.session.commit()


def _revoked_at(app, refid, real):
    with app.app_context():
        return RevokedSerial.query.filter_by(caref=refid, serial_number=str(real.serial_number)).one().revoked_at


class TestACrlUcmSignedPublishes:
    """A CRL UCM signed for a record of the issuer's key since the revocation may list it: the
    revocation was published, whatever its record says (a key held for a while, then gone)."""

    @pytest.mark.parametrize('external, published', [(False, True), (None, True), (True, False)])
    def test_a_crl_signed_since_the_revocation_publishes_it(
            self, app, auth_client, create_ca, external, published):
        ca = _keyless_ca(app, create_ca, f'Signed CRL 450 {external}')
        row_id, real = _leaf_row(app, ca, f'signed-crl-{external}')
        _revoke(auth_client, row_id)
        at = _revoked_at(app, ca[1], real)
        _signed_crl(app, ca[0], at - timedelta(seconds=1))
        assert _detail(auth_client, row_id)['local_revocation_lift'] == 'local'
        _signed_crl(app, ca[0], at, external=external)
        assert _records(app, ca[1], real) == [('superseded', False)]
        assert _detail(auth_client, row_id)['local_revocation_lift'] == (None if published else 'local')
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        if published:
            assert r.status_code == 409 and 'this revocation was published' in r.get_json()['message'], r.data
            assert _row(app, row_id)[0] is True
        else:
            assert r.status_code == 200, r.data

    def test_a_crl_of_a_twin_record_counts(self, app, auth_client, create_ca):
        ca = _keyless_ca(app, create_ca, 'Signed CRL 450 twin')
        row_id, real = _leaf_row(app, ca, 'twin-crl')
        _revoke(auth_client, row_id)
        now = datetime.now(timezone.utc)
        again = (x509.CertificateBuilder().subject_name(ca[2].subject).issuer_name(ca[2].subject)
                 .public_key(ca[3].public_key()).serial_number(x509.random_serial_number())
                 .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
                 .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                 .sign(ca[3], hashes.SHA256()))
        with app.app_context():
            original = db.session.get(CA, ca[0])
            twin = CA(refid=str(uuid.uuid4()), descr='keyless twin record', serial=0,
                      crt=base64.b64encode(again.public_bytes(serialization.Encoding.PEM)).decode(),
                      subject=original.subject, issuer=original.issuer)
            db.session.add(twin)
            db.session.commit()
            twin_id = twin.id
        assert _detail(auth_client, row_id)['local_revocation_lift'] == 'local'
        _signed_crl(app, twin_id, _revoked_at(app, ca[1], real))
        assert _detail(auth_client, row_id)['local_revocation_lift'] is None

    def test_an_unknown_record_a_signed_crl_may_list_is_published(self, app, auth_client, create_ca):
        ca = _keyless_ca(app, create_ca, 'Signed CRL 450 unknown')
        row_id, real = _leaf_row(app, ca, 'signed-crl-unknown')
        _record(app, ca[1], real, reason='superseded', certificate_id=row_id)
        assert _records(app, ca[1], real) == [('superseded', None)]
        assert _detail(auth_client, row_id)['local_revocation_lift'] == 'unknown'
        _signed_crl(app, ca[0], _revoked_at(app, ca[1], real) + timedelta(days=1))
        assert _detail(auth_client, row_id)['local_revocation_lift'] is None
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True, 'acknowledge_unknown_publication': True})
        assert r.status_code == 409 and 'this revocation was published' in r.get_json()['message'], r.data
        assert _records(app, ca[1], real) == [('superseded', None)]


class TestAKeyGainedPublishesTheRecords:
    """Once UCM holds a CA's key it signs its records: they stay published after the key goes."""

    def test_a_key_imported_then_lost_keeps_the_revocation(self, app, auth_client, create_ca):
        ca = _keyless_ca(app, create_ca, 'Key gained 450')
        row_id, real = _leaf_row(app, ca, 'key-route')
        _revoke(auth_client, row_id)
        assert _records(app, ca[1], real) == [('superseded', False)]
        r = _post(auth_client, f'/api/v2/cas/{ca[0]}/key', {'key': _key_pem(ca[3]).decode()})
        assert r.status_code == 200, r.data
        assert _records(app, ca[1], real) == [('superseded', True)]
        _drop_key(app, ca[0])
        assert _post(auth_client, LIFT.format(row_id), {'confirm': True}).status_code == 409
        assert _row(app, row_id)[0] is True

    def test_a_reimport_with_the_key_publishes_too(self, app, auth_client, create_ca):
        ca = _keyless_ca(app, create_ca, 'Key reimported 450')
        row_id, real = _leaf_row(app, ca, 'reimport')
        _revoke(auth_client, row_id)
        pem = ca[2].public_bytes(serialization.Encoding.PEM).decode() + _key_pem(ca[3]).decode()
        r = auth_client.post('/api/v2/cas/import', data={'pem_content': pem})
        assert r.status_code in (200, 201), r.data
        with app.app_context():
            assert db.session.get(CA, ca[0]).has_private_key
        assert _records(app, ca[1], real) == [('superseded', True)]

    @pytest.mark.parametrize('gain', ['prv', 'offline', 'responder'])
    def test_every_way_of_signing_for_the_ca_publishes(self, app, auth_client, create_ca, issuer, gain):
        ca = _keyless_ca(app, create_ca, f'Signs now 450 {gain}')
        row_id, real = _leaf_row(app, ca, f'gain-{gain}')
        _revoke(auth_client, row_id)
        responder = _leaf_row(app, issuer, 'gain-responder')[0] if gain == 'responder' else None
        with app.app_context():
            row = db.session.get(CA, ca[0])
            if gain == 'prv':
                row.prv = _stored_key(ca[3])
            elif gain == 'offline':
                row.offline, row.offline_mode = True, 'file_exported'
            else:
                db.session.add(SystemConfig(key=f'ocsp_responder_cert_{ca[0]}', value=str(responder)))
            db.session.commit()
        assert _records(app, ca[1], real) == [('superseded', True)]

    def test_a_key_imported_while_the_lift_runs_refuses_it(self, app, auth_client, create_ca):
        """PostgreSQL: the import holds the CA row and its records; the lift waits, then refuses."""
        self._race(app, auth_client, create_ca, orm=True)

    def test_a_key_written_by_sql_while_the_lift_runs_refuses_it(self, app, auth_client, create_ca):
        """PostgreSQL: a writer that leaves the records alone still holds the CA row the lift locks."""
        self._race(app, auth_client, create_ca, orm=False)

    def _race(self, app, auth_client, create_ca, orm):
        if not _on_postgresql(app):
            pytest.skip('row locks are PostgreSQL behaviour; SQLite serializes writers')
        ca = _keyless_ca(app, create_ca, f'Key race 450 {orm}')
        row_id, real = _leaf_row(app, ca, f'race-{orm}')
        _revoke(auth_client, row_id)
        with app.app_context():
            engine = db.engine
        holding, release, outcome = threading.Event(), threading.Event(), {}
        stored = _stored_key(ca[3])

        def import_the_key():
            with app.app_context():
                try:
                    if orm:
                        db.session.get(CA, ca[0]).prv = stored
                        db.session.flush()
                    else:
                        db.session.execute(CA.__table__.update().where(CA.__table__.c.id == ca[0])
                                           .values(prv=stored))
                    holding.set()
                    release.wait(30)
                    db.session.commit()
                except Exception as e:  # noqa: BLE001
                    db.session.rollback()
                    outcome['import'] = repr(e)
                finally:
                    holding.set()
                    db.session.remove()

        def release_once_the_lift_waits():
            with engine.connect() as conn:
                outcome['waited'] = _wait_for_a_lock_waiter(conn, 10)
            release.set()

        worker = threading.Thread(target=import_the_key)
        worker.start()
        assert holding.wait(30)
        releaser = threading.Thread(target=release_once_the_lift_waits)
        releaser.start()
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        worker.join(30)
        releaser.join(30)
        assert 'import' not in outcome and outcome.get('waited'), outcome
        assert r.status_code == 409, r.data
        assert _row(app, row_id)[0] is True
        _drop_key(app, ca[0])

    def test_a_key_written_while_the_lift_runs_is_seen_under_the_rows_lock(
            self, app, auth_client, create_ca, monkeypatch):
        """SQLite takes its write lock at the rows' UPDATE: what the CA gained before is read then."""
        from services.cert import issued_lookup
        ca = _keyless_ca(app, create_ca, 'Key meanwhile 450')
        row_id, _ = _leaf_row(app, ca, 'key-meanwhile')
        _revoke(auth_client, row_id)
        stored, lock, calls = _stored_key(ca[3]), issued_lookup.lock_serial_records, []

        def lock_then_gain_the_key(targets):
            calls.append(1)
            if len(calls) == 2:
                db.session.execute(CA.__table__.update().where(CA.__table__.c.id == ca[0]).values(prv=stored))
            return lock(targets)
        monkeypatch.setattr(issued_lookup, 'lock_serial_records', lock_then_gain_the_key)
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        assert r.status_code == 409, r.data
        assert len(calls) == 2 and _row(app, row_id)[0] is True


    def test_the_revocation_reads_its_issuer_afresh(self, app, auth_client, create_ca, monkeypatch):
        """A key another transaction committed after the revocation loaded its CA is seen."""
        from services.cert.mixins import lifecycle
        ca = _keyless_ca(app, create_ca, 'Key read afresh 450')
        row_id, real = _leaf_row(app, ca, 'read-afresh')
        stored, effective = _stored_key(ca[3]), lifecycle.effective_revocation

        def key_committed_meanwhile(certificate):
            db.session.execute(CA.__table__.update().where(CA.__table__.c.id == ca[0]).values(prv=stored))
            return effective(certificate)
        monkeypatch.setattr(lifecycle, 'effective_revocation', key_committed_meanwhile)
        _revoke(auth_client, row_id)
        assert _records(app, ca[1], real) == [('superseded', True)]
        _drop_key(app, ca[0])

    def test_a_key_imported_while_the_revocation_runs_publishes_its_record(
            self, app, auth_client, create_ca, monkeypatch):
        """PostgreSQL: the revocation reads its issuer under the CA rows' share lock, so a key
        import waits for it and publishes the record (the tests' SQLite is one connection)."""
        from services.cert import local_revocation
        if not _on_postgresql(app):
            pytest.skip('row locks are PostgreSQL behaviour; SQLite serializes writers')
        ca = _keyless_ca(app, create_ca, 'Key during revocation 450')
        row_id, real = _leaf_row(app, ca, 'during-revocation')
        stored, ask, workers, outcome = _stored_key(ca[3]), local_revocation.publishes_revocations, [], {}

        def import_the_key():
            with app.app_context():
                try:
                    db.session.get(CA, ca[0]).prv = stored
                    db.session.commit()
                except Exception as e:  # noqa: BLE001
                    db.session.rollback()
                    outcome['import'] = repr(e)
                finally:
                    db.session.remove()

        def import_while_asked(target):
            answer = ask(target)
            if not workers:
                workers.append(threading.Thread(target=import_the_key))
                workers[0].start()
                workers[0].join(2)  # at once, unless the revocation's lock makes it wait
            return answer
        monkeypatch.setattr(local_revocation, 'publishes_revocations', import_while_asked)
        _revoke(auth_client, row_id)
        workers[0].join(30)
        assert 'import' not in outcome, outcome
        assert _records(app, ca[1], real) == [('superseded', True)]
        _drop_key(app, ca[0])
        assert _post(auth_client, LIFT.format(row_id), {'confirm': True}).status_code == 409

    def test_a_responder_given_its_key_later_publishes(self, app, auth_client, create_ca, issuer):
        ca = _keyless_ca(app, create_ca, 'Responder key later 450')
        responder, responder_real = _leaf_row(app, issuer, 'keyless-responder')
        with app.app_context():
            row = db.session.get(Certificate, responder)
            key, row.prv = row.prv, None
            db.session.add(SystemConfig(key=f'ocsp_responder_cert_{ca[0]}', value=str(responder)))
            db.session.commit()
        row_id, real = _leaf_row(app, ca, 'responder-later')
        _revoke(auth_client, row_id)
        assert _records(app, ca[1], real) == [('superseded', False)]
        with app.app_context():
            db.session.get(Certificate, responder).prv = key
            db.session.commit()
        assert _records(app, ca[1], real) == [('superseded', True)]

    def test_a_responder_rebound_by_its_renewal_publishes(self, app, auth_client, create_ca, issuer):
        from services.ocsp_responder_renewal import _rebind
        ca = _keyless_ca(app, create_ca, 'Responder rebound 450')
        old, _ = _leaf_row(app, issuer, 'responder-old')
        new, _ = _leaf_row(app, issuer, 'responder-new')
        key = f'ocsp_responder_cert_{ca[0]}'
        with app.app_context():
            db.session.get(Certificate, old).prv = None
            db.session.add(SystemConfig(key=key, value=str(old)))
            db.session.commit()
        row_id, real = _leaf_row(app, ca, 'responder-rebound')
        _revoke(auth_client, row_id)
        assert _records(app, ca[1], real) == [('superseded', False)]
        with app.app_context():
            assert _rebind(key, old, new)
            db.session.commit()
        assert _records(app, ca[1], real) == [('superseded', True)]


class TestARevocationToldToItsIssuer:
    """A Microsoft CA or an ACME CA is told of the revocation: it publishes it, UCM cannot lift it."""

    @pytest.mark.parametrize('source', ['msca', 'acme_client'])
    def test_a_copy_of_such_a_source_is_never_lifted(self, app, auth_client, keyless, source):
        row_id, real = _leaf_row(app, keyless, f'told-{source}')
        with app.app_context():
            db.session.get(Certificate, row_id).source = source
            db.session.commit()
        _revoke(auth_client, row_id)
        assert _detail(auth_client, row_id)['local_revocation_lift'] is None
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        assert r.status_code == 409 and 'outside UCM' in r.get_json()['message'], r.data
        assert _row(app, row_id)[0] is True

    def _revoked(self, app, auth_client, keyless, source):
        row_id, real = _leaf_row(app, keyless, f'propagated-{source}')
        _record(app, keyless[1], real, reason='superseded', certificate_id=row_id)
        with app.app_context():
            RevokedSerial.query.filter_by(certificate_id=row_id).update({'published': False})
            row = db.session.get(Certificate, row_id)
            row.source, row.revoked, row.revoke_reason = source, True, 'superseded'
            db.session.commit()
        return row_id, real

    @pytest.mark.parametrize('sent, outcome', [(None, 'revoked'), ('CA unreachable', 'owed')])
    def test_a_revocation_sent_or_owed_to_the_acme_ca_is_published(
            self, app, auth_client, keyless, monkeypatch, sent, outcome):
        from types import SimpleNamespace
        from services import acme_renewal_service
        from services.acme import upstream_revocation
        row_id, real = self._revoked(app, auth_client, keyless, 'acme_client')
        monkeypatch.setattr(upstream_revocation, '_order_for', lambda cert: SimpleNamespace(id=1))
        monkeypatch.setattr(upstream_revocation, '_client_for', lambda order: object())
        monkeypatch.setattr(acme_renewal_service, 'send_upstream_revocation', lambda *a: sent)
        monkeypatch.setattr(acme_renewal_service, '_owe_upstream_revocation', lambda *a: True)
        with app.app_context():
            result = upstream_revocation.propagate_acme_revocation(
                db.session.get(Certificate, row_id), 'superseded')
        assert result[0] == outcome
        assert _records(app, keyless[1], real) == [('superseded', True)]

    def test_a_revocation_propagated_to_the_microsoft_ca_is_published(
            self, app, auth_client, keyless, monkeypatch):
        from types import SimpleNamespace
        from services.msca import propagation
        from services.msca_service import MicrosoftCAService
        row_id, real = self._revoked(app, auth_client, keyless, 'msca')
        monkeypatch.setattr(propagation, 'find_msca_for_cert', lambda cert: SimpleNamespace(name='AD CS'))
        monkeypatch.setattr(MicrosoftCAService, 'admin_channel_available', staticmethod(lambda msca: True))
        monkeypatch.setattr(MicrosoftCAService, 'revoke_on_ca', staticmethod(lambda *a, **k: None))
        with app.app_context():
            outcome, _ = propagation.propagate_revocation(db.session.get(Certificate, row_id), 'superseded')
        assert outcome == propagation.PROPAGATED
        assert _records(app, keyless[1], real) == [('superseded', True)]


class TestDeletingACertificateItsIssuerIsToldOf:
    @pytest.mark.parametrize('source', ['msca', 'acme_client'])
    def test_a_valid_one_linked_to_no_ca_is_revoked_first(self, app, auth_client, keyless, source):
        _, _, ca_cert, ca_key = keyless
        real, key = _leaf(f'unlinked-{source}-{uuid.uuid4().hex[:6]}.example.test', ca_cert, ca_key, days=200)
        row_id = _store(app, real, None, key=key)
        with app.app_context():
            db.session.get(Certificate, row_id).source = source
            db.session.commit()
        assert _detail(auth_client, row_id)['revocation_published'] is True
        r = auth_client.delete(f'/api/v2/certificates/{row_id}')
        assert r.status_code == 409 and b'revoke it first' in r.data
        bulk = _post(auth_client, '/api/v2/certificates/bulk/delete', {'ids': [row_id]})
        assert bulk.get_json()['data']['failed'][0]['id'] == row_id
        assert _exists(app, row_id)

    def test_the_bulk_route_asks_once_per_ca(self, app, auth_client, keyless, monkeypatch):
        from services.cert import local_revocation
        ids = [_leaf_row(app, keyless, f'bulk-once-{i}')[0] for i in range(3)]
        asked, ask = [], local_revocation.publishes_revocations

        def counted(ca):
            asked.append(ca.refid if ca is not None else None)
            return ask(ca)
        monkeypatch.setattr(local_revocation, 'publishes_revocations', counted)
        r = _post(auth_client, '/api/v2/certificates/bulk/delete', {'ids': ids})
        assert r.get_json()['data']['success'] == ids, r.data
        assert asked == [keyless[1]]


class TestALiftedCompromiseKeepsItsKeyRefused:
    def test_the_key_stays_refused_once_its_records_go(self, app, auth_client, keyless):
        from services.acme.compromised_keys import key_revoked_as_compromised
        from utils.spki_digest import public_key_sha256
        row_id, real = _leaf_row(app, keyless, 'compromise-kept')
        _record(app, keyless[1], real, reason='keyCompromise', certificate_id=row_id)
        with app.app_context():
            RevokedSerial.query.filter_by(certificate_id=row_id).update(
                {'published': False, 'public_key_sha256': public_key_sha256(real.public_key())})
            db.session.commit()
            assert key_revoked_as_compromised(real.public_key())
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        assert r.status_code == 200, r.data
        assert _records(app, keyless[1], real) == [] and _row(app, row_id)[0] is False
        with app.app_context():
            assert key_revoked_as_compromised(real.public_key())

    def test_a_key_that_cannot_be_kept_refuses_the_lift(self, app, auth_client, keyless, monkeypatch):
        from models import compromised_key
        row_id, real = _leaf_row(app, keyless, 'compromise-unkept')
        _revoke(auth_client, row_id, 'keyCompromise')
        with app.app_context():
            compromised_key.CompromisedKeyRecord.query.filter_by(cert_refid=db.session.get(
                Certificate, row_id).refid).delete()
            db.session.commit()
        monkeypatch.setattr(compromised_key, 'remember_compromised_key', lambda *a, **k: False)
        r = _post(auth_client, LIFT.format(row_id), {'confirm': True})
        assert r.status_code == 500 and 'compromised' in r.get_json()['message'], r.data
        assert _row(app, row_id)[0] is True
