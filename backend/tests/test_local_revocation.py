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

import pytest
from cryptography import x509

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


def _leaf_row(app, issuer, cn, caref=None):
    _, refid, ca_cert, ca_key = issuer
    real, key = _leaf(f'{cn}-{uuid.uuid4().hex[:6]}.example.test', ca_cert, ca_key, days=200)
    return _store(app, real, refid if caref is None else caref, key=key), real


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
        row_id, _ = _leaf_row(app, keyless, 'unlinked', caref='')
        with app.app_context():
            db.session.get(Certificate, row_id).caref = None
            db.session.commit()
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
        assert _post(auth_client, LIFT.format(row_id), {'confirm': True}).status_code == 409
        assert _records(app, keyless[1], real) == [('superseded', True)]

    def test_a_ca_that_publishes_now_refuses_a_local_record(self, app, auth_client, keyless, issuer, ca_state):
        row_id, real = _leaf_row(app, keyless, 'publishes-now')
        _revoke(auth_client, row_id)
        _responder(app, keyless[0], issuer)
        assert _post(auth_client, LIFT.format(row_id), {'confirm': True}).status_code == 409
        assert _records(app, keyless[1], real) == [('superseded', False)]

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

    def test_a_row_revoked_without_a_record_is_of_unknown_publication(self, app, auth_client, keyless):
        row_id, _ = _leaf_row(app, keyless, 'row-only')
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            row.revoked, row.revoke_reason = True, 'superseded'
            db.session.commit()
        assert _detail(auth_client, row_id)['local_revocation_lift'] == 'unknown'

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
