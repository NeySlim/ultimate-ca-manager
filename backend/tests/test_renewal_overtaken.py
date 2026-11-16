"""A renewal overtaken by another one is refused as renewed meanwhile, never as revoked.

The winner records the old serial as superseded: a caller still holding the row it read
before must not read that record as a revocation of the certificate.
"""
import os
import threading
import uuid

import pytest
from cryptography import x509

from models import Certificate, db
from tests.test_renewal_concurrency_pg import _leaf

_PG_URL = os.environ.get('UCM_TEST_PG_URL')


def _renew_elsewhere(app, cert_id):
    """Renew ``cert_id`` to completion in a session of its own."""
    from services.cert.renewal import renew_certificate_in_place

    done = {}

    def run():
        with app.app_context():
            try:
                done['serial'] = renew_certificate_in_place(
                    db.session.get(Certificate, cert_id), username='admin',
                    regenerate_crl=False)['new_serial']
            finally:
                db.session.remove()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(60)
    assert done.get('serial'), done


def _stale_check(app, cert_id):
    from services.cert.renewal import RenewalError, check_renewable
    with app.app_context():
        cert = db.session.get(Certificate, cert_id)
        _renew_elsewhere(app, cert_id)
        with pytest.raises(RenewalError) as e:
            check_renewable(cert)
        db.session.remove()
    return e.value


def test_the_routes_check_on_a_row_renewed_since_read_on_sqlite(app, tmp_path):
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'overtaken.db'}"):
        cert_id, _, _ = _leaf(app)
        refusal = _stale_check(app, cert_id)
    assert refusal.status == 409 and 'renewed by another request' in refusal.message, refusal.message


def _delete_elsewhere(app, cert_id):
    def run():
        with app.app_context():
            Certificate.query.filter_by(id=cert_id).delete()
            db.session.commit()
            db.session.remove()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(60)


def test_a_row_deleted_since_read_is_gone_not_revoked(app, tmp_path):
    """The record of its old serial stays; the row it was read from does not."""
    from services.cert.renewal import RenewalError, check_renewable
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'deleted.db'}"):
        cert_id, _, _ = _leaf(app)
        with app.app_context():
            cert = db.session.get(Certificate, cert_id)
            _renew_elsewhere(app, cert_id)
            _delete_elsewhere(app, cert_id)
            with pytest.raises(RenewalError) as e:
                check_renewable(cert)
            db.session.remove()
    assert e.value.status == 404 and 'no longer exists' in e.value.message, e.value.message


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_the_routes_check_on_a_row_renewed_since_read_on_postgresql(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'renew_overtaken_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        cert_id, _, _ = _leaf(app)
        refusal = _stale_check(app, cert_id)
    assert refusal.status == 409 and 'renewed by another request' in refusal.message, refusal.message


def _overtaken_after(monkeypatch, app, cert_id, step):
    """The other renewal commits right after ``step`` of this one has run (SQLite only:
    on PostgreSQL the row stays locked from the re-read to the commit)."""
    from services.cert import renewal
    real, fired = getattr(renewal, step), []

    def then_overtaken(*args, **kwargs):
        result = real(*args, **kwargs)
        if not fired:
            fired.append(True)
            _renew_elsewhere(app, cert_id)
        return result

    monkeypatch.setattr(renewal, step, then_overtaken)
    return fired


@pytest.mark.parametrize('step', ['_reread', 'check_renewable'])
@pytest.mark.parametrize('trigger', ['manual', 'auto'])
def test_a_renewal_overtaken_midway_says_renewed(app, tmp_path, monkeypatch, step, trigger):
    from services.auto_renewal_service import AutoRenewalService
    from services.cert.renewal import RenewalError, renew_certificate_in_place
    from tests.test_backup_cross_installation import _bound_to

    with _bound_to(app, f"sqlite:///{tmp_path / 'overtaken.db'}"):
        cert_id, _, _ = _leaf(app)
        fired = _overtaken_after(monkeypatch, app, cert_id, step)
        with app.app_context():
            cert = db.session.get(Certificate, cert_id)
            if trigger == 'auto':
                outcome = AutoRenewalService.renew_certificate(cert, regenerate_crl=False)
            else:
                try:
                    renew_certificate_in_place(cert, username='admin', regenerate_crl=False)
                    outcome = None
                except RenewalError as e:
                    db.session.rollback()
                    outcome = (e.status, e.message)
            db.session.remove()
    assert fired
    if trigger == 'auto':  # a race the next pass retries: skipped, not failed
        assert outcome == (None, 'Certificate was renewed by another request'), outcome
    else:
        assert outcome is not None and outcome[0] == 409, outcome
        assert 'renewed by another request' in outcome[1], outcome


def _auto_pass(app, monkeypatch, cert_id):
    """One scheduler pass over ``cert_id``: ``(stats, failure mails, failure audits)``."""
    from models import AuditLog
    from services.auto_renewal_service import AutoRenewalService as svc
    sent = []
    monkeypatch.setattr(svc, '_send_failure_notification', staticmethod(lambda stats: sent.append(stats)))
    monkeypatch.setattr(svc, '_held_for_approval', staticmethod(lambda cert, already_queued: None))
    monkeypatch.setattr(svc, '_publish_crls', staticmethod(lambda carefs: None))
    with app.app_context():
        svc.set_renewal_config({'enabled': True, 'notify_on_failure': True})
        monkeypatch.setattr(svc, 'get_certificates_for_renewal',
                            staticmethod(lambda: [db.session.get(Certificate, cert_id)]))
        stats = svc.run_auto_renewal()
        audits = AuditLog.query.filter_by(action='certificate.auto_renewal_failed').count()
        db.session.remove()
    return stats, sent, audits


def test_a_scheduled_renewal_overtaken_is_skipped_without_a_failure(app, tmp_path, monkeypatch):
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'auto-overtaken.db'}"):
        cert_id, _, _ = _leaf(app)
        fired = _overtaken_after(monkeypatch, app, cert_id, '_reread')
        stats, sent, audits = _auto_pass(app, monkeypatch, cert_id)
    assert fired
    assert (stats['renewed'], stats['failed'], stats['skipped']) == (0, 0, 1), stats
    assert (sent, audits) == ([], 0)


def test_a_scheduled_renewal_refused_otherwise_still_fails(app, tmp_path, monkeypatch):
    """Only the two races are skipped: any other 409 is a failure, mailed and audited."""
    from services import auto_renewal_service
    from services.cert.renewal import RenewalError
    from tests.test_backup_cross_installation import _bound_to

    def refused(*args, **kwargs):
        raise RenewalError('Cannot renew a revoked certificate. Issue a new certificate instead.', 409)

    with _bound_to(app, f"sqlite:///{tmp_path / 'auto-refused.db'}"):
        cert_id, _, _ = _leaf(app)
        monkeypatch.setattr(auto_renewal_service, 'renew_certificate_in_place', refused)
        stats, sent, audits = _auto_pass(app, monkeypatch, cert_id)
    assert (stats['failed'], stats['skipped']) == (1, 0), stats
    assert len(sent) == 1 and audits == 1


# ---- a related pair (RFC 9763): the partner is judged as stored now ---------------------

def _linked_rows(app, n_b=1):
    """Certificate A and ``n_b`` certificates B naming it, keys held by the server; the last
    B and A name each other. ``(a_id, [b_ids])``."""
    import base64
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from services.cert.related_pair import pq_builder_from
    from utils.key_codec import store_pem_bytes
    from utils.serial_format import canonical_serial

    a_id, _, _ = _leaf(app)
    with app.app_context():
        from models import CA
        from services.hsm.ca_key_loader import get_ca_signing_key
        a = db.session.get(Certificate, a_id)
        ca = CA.query.filter_by(refid=a.caref).one()
        ca_key = get_ca_signing_key(ca)
        cert_a = x509.load_pem_x509_certificate(base64.b64decode(a.crt))
        b_ids = []
        for _ in range(n_b):
            key = ec.generate_private_key(ec.SECP256R1())
            cert_b = pq_builder_from(cert_a, key.public_key()).sign(ca_key, hashes.SHA256())
            b = Certificate(
                refid=uuid.uuid4().hex, descr='b', caref=a.caref, cert_type=a.cert_type,
                crt=base64.b64encode(cert_b.public_bytes(serialization.Encoding.PEM)).decode(),
                prv=store_pem_bytes(key.private_bytes(
                    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption())),
                subject=a.subject, issuer=a.issuer, serial_number=canonical_serial(cert_b.serial_number),
                valid_from=cert_b.not_valid_before_utc.replace(tzinfo=None),
                valid_to=cert_b.not_valid_after_utc.replace(tzinfo=None), source=a.source,
                related_certificate_id=a_id)
            db.session.add(b)
            db.session.flush()
            b_ids.append(b.id)
        a.related_certificate_id = b_ids[-1]
        db.session.commit()
        db.session.remove()
    return a_id, b_ids


def _names(row):
    import base64
    from services.cert.related_pair import row_certificate
    from utils import related_cert
    return related_cert.references(x509.load_pem_x509_certificate(base64.b64decode(row.crt)),
                                   row_certificate(db.session.get(Certificate, row.related_certificate_id)))


def _a_partner_renewed_since_read(app):
    """B read by this session, then the pair renewed elsewhere: A still renews with B."""
    from services.cert.renewal import renew_certificate_in_place, renewal_partner
    a_id, (b_id,) = _linked_rows(app)
    with app.app_context():
        held = db.session.get(Certificate, b_id)  # kept by the session as it was read
        _renew_elsewhere(app, b_id)
        a = db.session.get(Certificate, a_id)
        partner = renewal_partner(a)
        assert partner is not None and partner.id == b_id
        outcome = renew_certificate_in_place(a, username='admin', regenerate_crl=False)
        assert [r['cert_id'] for r in outcome['related']] == [b_id], outcome
        db.session.expire_all()
        a, b = db.session.get(Certificate, a_id), db.session.get(Certificate, b_id)
        assert (a.renewed_times, b.renewed_times) == (2, 2)
        assert (a.related_certificate_id, b.related_certificate_id) == (b_id, a_id)
        assert _names(b) and held is b
        db.session.remove()


def _an_a_renewed_since_read(app):
    """A read by this session, then renewed elsewhere with its newest B: an older B renewed
    alone still names A's current certificate."""
    from services.cert.renewal import renew_certificate_in_place
    a_id, (old_b, new_b) = _linked_rows(app, n_b=2)
    with app.app_context():
        held = db.session.get(Certificate, a_id)  # kept by the session as it was read
        _renew_elsewhere(app, a_id)
        b = db.session.get(Certificate, old_b)
        outcome = renew_certificate_in_place(b, username='admin', regenerate_crl=False)
        assert outcome['related'] == [], outcome
        db.session.expire_all()
        b = db.session.get(Certificate, old_b)
        assert b.related_certificate_id == a_id and _names(b) and held is not b
        db.session.remove()


@pytest.mark.parametrize('case', [_a_partner_renewed_since_read, _an_a_renewed_since_read])
def test_a_member_renewed_since_read_is_not_revoked_on_sqlite(app, tmp_path, case):
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'pair.db'}"):
        case(app)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('case', [_a_partner_renewed_since_read, _an_a_renewed_since_read])
def test_a_member_renewed_since_read_is_not_revoked_on_postgresql(app, case):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'renew_pair_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        case(app)


def _revoke_elsewhere(app, row_id, how):
    """Revoke ``row_id`` in a session of its own: on hold by its row alone, or by the record
    of the serial it carries now."""
    import base64
    from models import RevokedSerial
    from utils.datetime_utils import utc_now

    def run():
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            if how == 'row':
                row.revoked, row.revoke_reason, row.revoked_at = True, 'certificateHold', utc_now()
            else:
                serial = x509.load_pem_x509_certificate(base64.b64decode(row.crt)).serial_number
                db.session.add(RevokedSerial(caref=row.caref, serial_number=str(serial),
                                             revoke_reason='keyCompromise', certificate_id=row_id,
                                             valid_to=row.valid_to))
            db.session.commit()
            db.session.remove()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(60)


@pytest.mark.parametrize('how', ['row', 'record'])
def test_a_partner_revoked_since_read_lets_the_member_renew_alone(app, tmp_path, how):
    from services.cert.renewal import renewal_partner
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'revoked.db'}"):
        a_id, (b_id,) = _linked_rows(app)
        with app.app_context():
            a = db.session.get(Certificate, a_id)
            held = renewal_partner(a)  # B kept by the session, unrevoked
            assert held.id == b_id
            _revoke_elsewhere(app, b_id, how)
            assert renewal_partner(a) is None and held.revoked == (how == 'row')
            db.session.remove()


@pytest.mark.parametrize('how', ['row', 'record'])
def test_an_a_revoked_since_read_is_not_named(app, tmp_path, how):
    from services.cert.renewal import _current_related
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'revoked_a.db'}"):
        a_id, (old_b, _new_b) = _linked_rows(app, n_b=2)
        with app.app_context():
            b = db.session.get(Certificate, old_b)
            held = db.session.get(Certificate, a_id)  # kept by the session, unrevoked
            assert _current_related(b) is not None
            _revoke_elsewhere(app, a_id, how)
            assert _current_related(b) is None and held.revoked == (how == 'row')
            db.session.remove()


def test_a_partner_that_left_the_pair_since_read_is_not_renewed_with_it(app, tmp_path):
    from services.cert.renewal import renewal_partner
    from tests.test_backup_cross_installation import _bound_to

    def leave(b_id):
        with app.app_context():
            db.session.get(Certificate, b_id).related_certificate_id = None
            db.session.commit()
            db.session.remove()

    with _bound_to(app, f"sqlite:///{tmp_path / 'left.db'}"):
        a_id, (b_id,) = _linked_rows(app)
        with app.app_context():
            a = db.session.get(Certificate, a_id)
            held = renewal_partner(a)  # B kept by the session, still naming A
            assert held.id == b_id
            thread = threading.Thread(target=leave, args=(b_id,))
            thread.start()
            thread.join(60)
            assert renewal_partner(a) is None and held.related_certificate_id is None
            db.session.remove()


def _linked_elsewhere(app, a_id, b_id):
    """What link_issued stores when a newer B takes A: both name each other."""
    def link():
        with app.app_context():
            db.session.get(Certificate, a_id).related_certificate_id = b_id
            db.session.get(Certificate, b_id).related_certificate_id = a_id
            db.session.commit()
            db.session.remove()

    thread = threading.Thread(target=link)
    thread.start()
    thread.join(60)


@pytest.mark.parametrize('read_with', ['the previous B', 'no B'])
def test_a_certificate_given_a_newer_partner_since_read_renews_with_it(app, tmp_path, read_with):
    """The link of the renewed certificate itself is the stored one, not the caller's copy:
    the previous B, which still names A, is not renewed in the newer one's place."""
    from services.cert.renewal import renewal_partner
    from tests.test_backup_cross_installation import _bound_to

    with _bound_to(app, f"sqlite:///{tmp_path / 'newer.db'}"):
        a_id, (first, newer) = _linked_rows(app, n_b=2)
        with app.app_context():
            a = db.session.get(Certificate, a_id)
            a.related_certificate_id = first if read_with == 'the previous B' else None
            db.session.commit()
            serial = db.session.get(Certificate, a_id).serial_number  # A as the caller read it
            assert getattr(renewal_partner(a), 'id', None) == (
                first if read_with == 'the previous B' else None)
            _linked_elsewhere(app, a_id, newer)
            assert renewal_partner(a).id == newer
            # The caller's copy is left as read: its serial is what refuses a doubled renewal
            assert a.related_certificate_id == (first if read_with == 'the previous B' else None)
            assert a.serial_number == serial
            db.session.remove()


def _read_then_given_a_newer_partner(app, read_with):
    a_id, (first, newer) = _linked_rows(app, n_b=2)
    a = db.session.get(Certificate, a_id)
    a.related_certificate_id = first if read_with == 'the previous B' else None
    db.session.commit()
    assert a.serial_number  # read again, as a route holds it
    return a, first, newer


@pytest.mark.parametrize('read_with', ['the previous B', 'no B'])
def test_a_certificate_given_a_newer_partner_is_renewed_with_it_alone(app, tmp_path, read_with):
    """To the end: the newer B is renewed and names the renewed A, the previous one is left."""
    from services.cert.renewal import renew_certificate_in_place
    from tests.test_backup_cross_installation import _bound_to

    with _bound_to(app, f"sqlite:///{tmp_path / 'newer-end.db'}"):
        with app.app_context():
            a, first, newer = _read_then_given_a_newer_partner(app, read_with)
            a_id, left = a.id, db.session.get(Certificate, first).serial_number
            _linked_elsewhere(app, a_id, newer)
            outcome = renew_certificate_in_place(a, username='admin', regenerate_crl=False)
            assert [r['cert_id'] for r in outcome['related']] == [newer]
            db.session.expire_all()
            a, b = db.session.get(Certificate, a_id), db.session.get(Certificate, newer)
            assert (a.related_certificate_id, b.related_certificate_id) == (newer, a_id)
            assert _names(b) and b.renewed_times == 1
            previous = db.session.get(Certificate, first)
            assert previous.serial_number == left and not previous.renewed_times
            db.session.remove()


@pytest.mark.parametrize('trigger', ['manual', 'auto'])
@pytest.mark.parametrize('read_with', ['the previous B', 'no B'])
def test_a_partner_taken_while_the_members_were_chosen_refuses_the_renewal(
        app, tmp_path, monkeypatch, read_with, trigger):
    """The link is judged again on the row as the renewal locks it: nothing is renewed on a
    choice made before a newer B took the certificate, and a retry renews with that B."""
    from services.cert import renewal
    from tests.test_backup_cross_installation import _bound_to

    with _bound_to(app, f"sqlite:///{tmp_path / 'taken.db'}"):
        with app.app_context():
            a, first, newer = _read_then_given_a_newer_partner(app, read_with)
            a_id, serials = a.id, {}
            for row_id in (a_id, first, newer):
                serials[row_id] = db.session.get(Certificate, row_id).serial_number
            chosen = renewal._linked_members

            def then_taken(cert):
                members = chosen(cert)
                _linked_elsewhere(app, a_id, newer)
                return members

            monkeypatch.setattr(renewal, '_linked_members', then_taken)
            with pytest.raises(renewal.RenewalError) as e:
                renewal.renew_certificate_in_place(a, username='admin', regenerate_crl=False,
                                                   trigger=trigger)
            monkeypatch.undo()
            said = 'The related pair was changed by another request'
            assert (e.value.status, e.value.message, e.value.overtaken) == (
                409, said if trigger == 'auto' else f'{said}; reload it and retry', True)
            db.session.expire_all()
            for row_id, serial in serials.items():
                assert db.session.get(Certificate, row_id).serial_number == serial
            outcome = renewal.renew_certificate_in_place(
                db.session.get(Certificate, a_id), username='admin', regenerate_crl=False)
            assert [r['cert_id'] for r in outcome['related']] == [newer]
            db.session.remove()


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_a_partner_taken_under_the_lock_the_renewal_waits_on_refuses_it_on_postgresql(app, monkeypatch):
    from services.cert import renewal
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_renewal_lock_order_pg import _own_session, _pid_of, _waits_on_a_lock
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'renew_taken_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        a_id, (first, newer) = _linked_rows(app, n_b=2)
        with app.app_context():
            db.session.get(Certificate, a_id).related_certificate_id = first
            db.session.commit()
            serials = {i: db.session.get(Certificate, i).serial_number for i in (a_id, first, newer)}
            db.session.remove()
        holds, release, pids, outcome = threading.Event(), threading.Event(), {}, {}

        def take_a():  # link_issued: A locked, link moved, committed later
            with app.app_context():
                engine, pids['linker'] = _own_session(url)
                try:
                    row = db.session.get(Certificate, a_id, with_for_update=True)
                    row.related_certificate_id = newer
                    db.session.flush()
                    holds.set()
                    release.wait(30)
                    db.session.commit()
                finally:
                    holds.set()
                    db.session.remove()
                    engine.dispose()

        linker, chosen = threading.Thread(target=take_a), renewal._linked_members

        def then_taken(cert):
            members = chosen(cert)
            linker.start()
            assert holds.wait(30)
            return members

        def renew():
            with app.app_context():
                engine, pids['renewal'] = _own_session(url)
                try:
                    renewal.renew_certificate_in_place(db.session.get(Certificate, a_id),
                                                       username='admin', regenerate_crl=False)
                    outcome['renewed'] = True
                except renewal.RenewalError as e:
                    outcome['error'] = (e.status, e.message)
                finally:
                    db.session.remove()
                    engine.dispose()

        monkeypatch.setattr(renewal, '_linked_members', then_taken)
        renewer = threading.Thread(target=renew)
        renewer.start()
        blocked = _waits_on_a_lock(url, _pid_of(pids, 'renewal'))
        release.set()
        renewer.join(60)
        linker.join(60)
        monkeypatch.undo()
        assert blocked, outcome
        assert outcome.get('error', (None, ''))[0] == 409, outcome
        with app.app_context():
            for row_id, serial in serials.items():
                assert db.session.get(Certificate, row_id).serial_number == serial
            done = renewal.renew_certificate_in_place(db.session.get(Certificate, a_id),
                                                      username='admin', regenerate_crl=False)
            assert [r['cert_id'] for r in done['related']] == [newer]
            db.session.remove()


def test_a_partner_that_left_while_the_members_were_chosen_refuses_the_renewal(
        app, tmp_path, monkeypatch):
    """Each member is judged on its own stored link, B as well as A."""
    from services.cert import renewal
    from tests.test_backup_cross_installation import _bound_to

    def leave(b_id):
        with app.app_context():
            db.session.get(Certificate, b_id).related_certificate_id = None
            db.session.commit()
            db.session.remove()

    with _bound_to(app, f"sqlite:///{tmp_path / 'left-late.db'}"):
        a_id, (b_id,) = _linked_rows(app)
        with app.app_context():
            a = db.session.get(Certificate, a_id)
            serial, chosen = a.serial_number, renewal._linked_members

            def then_left(cert):
                members = chosen(cert)
                thread = threading.Thread(target=leave, args=(b_id,))
                thread.start()
                thread.join(60)
                return members

            monkeypatch.setattr(renewal, '_linked_members', then_left)
            with pytest.raises(renewal.RenewalError) as e:
                renewal.renew_certificate_in_place(a, username='admin', regenerate_crl=False)
            monkeypatch.undo()
            assert (e.value.status, e.value.message, e.value.overtaken) == (409, (
                f'Related certificate {b_id}: The related pair was changed by another request; '
                'reload it and retry'), True)
            db.session.expire_all()
            assert db.session.get(Certificate, a_id).serial_number == serial
            db.session.remove()


def _chain_pair(app):
    """``(a_id, b_id)``: A names X in its certificate, B names A, A and B link each other."""
    import base64
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from services.cert.related_pair import pq_builder_from
    from services.hsm.ca_key_loader import get_ca_signing_key
    from models import CA
    from utils.key_codec import store_pem_bytes
    from utils.serial_format import canonical_serial

    _x_id, (a_id,) = _linked_rows(app)
    with app.app_context():
        a = db.session.get(Certificate, a_id)
        ca = CA.query.filter_by(refid=a.caref).one()
        cert_a = x509.load_pem_x509_certificate(base64.b64decode(a.crt))
        key = ec.generate_private_key(ec.SECP256R1())
        cert_b = pq_builder_from(cert_a, key.public_key()).sign(get_ca_signing_key(ca), hashes.SHA256())
        b = Certificate(
            refid=uuid.uuid4().hex, descr='b', caref=a.caref, cert_type=a.cert_type,
            crt=base64.b64encode(cert_b.public_bytes(serialization.Encoding.PEM)).decode(),
            prv=store_pem_bytes(key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption())),
            subject=a.subject, issuer=a.issuer, serial_number=canonical_serial(cert_b.serial_number),
            valid_from=cert_b.not_valid_before_utc.replace(tzinfo=None),
            valid_to=cert_b.not_valid_after_utc.replace(tzinfo=None), source=a.source,
            related_certificate_id=a_id)
        db.session.add(b)
        db.session.flush()
        a.related_certificate_id = b_id = b.id
        db.session.commit()
        db.session.remove()
    return a_id, b_id


def _names_none(row):
    import base64
    from utils import related_cert
    return related_cert.read_related_certificate(
        x509.load_pem_x509_certificate(base64.b64decode(row.crt))) is None


def test_a_b_unlinked_since_read_renews_alone_naming_none(app, tmp_path):
    """Old B read naming A; elsewhere the newest B goes on hold and A renews alone, which unlinks
    old B. Renewed from the caller's copy, old B names nothing and stays out of the pair."""
    from services.cert.renewal import renew_certificate_in_place
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'unlinked.db'}"):
        a_id, (old_b, new_b) = _linked_rows(app, n_b=2)
        with app.app_context():
            held = db.session.get(Certificate, old_b)  # kept by the session, linked to A
            assert held.related_certificate_id == a_id
            _revoke_elsewhere(app, new_b, 'row')
            _renew_elsewhere(app, a_id)
            outcome = renew_certificate_in_place(held, username='admin', regenerate_crl=False)
            assert outcome['related'] == [], outcome
            db.session.expire_all()
            b = db.session.get(Certificate, old_b)
            assert b.renewed_times == 1
            assert b.related_certificate_id is None and _names_none(b)
            db.session.remove()


@pytest.mark.parametrize('x', ['held', 'deleted'])
def test_a_chain_pair_renews_a_naming_nothing_its_original_did_not(app, tmp_path, x):
    """A names X and links to its own B: the link is B's way back, not A's A. Renewed with B,
    A' never names B's replaced certificate; B' names A'."""
    import base64
    from services.cert.related_pair import row_certificate
    from services.cert.renewal import renew_certificate_in_place
    from services.cert_service import CertificateService
    from tests.test_backup_cross_installation import _bound_to
    from utils import related_cert
    with _bound_to(app, f"sqlite:///{tmp_path / 'chain.db'}"):
        a_id, b_id = _chain_pair(app)
        with app.app_context():
            x_id = Certificate.query.filter(Certificate.related_certificate_id == a_id,
                                            Certificate.id != b_id).one().id
            if x == 'deleted':
                assert CertificateService.delete_certificate(x_id)
                db.session.expire_all()
                assert db.session.get(Certificate, a_id).related_certificate_id == b_id
            old_b = row_certificate(db.session.get(Certificate, b_id))
            outcome = renew_certificate_in_place(db.session.get(Certificate, a_id), username='admin',
                                                 regenerate_crl=False)
            assert [r['cert_id'] for r in outcome['related']] == [b_id]
            db.session.expire_all()
            a, b = db.session.get(Certificate, a_id), db.session.get(Certificate, b_id)
            cert_a = x509.load_pem_x509_certificate(base64.b64decode(a.crt))
            assert not related_cert.references(cert_a, old_b)
            assert _names_none(a)
            assert related_cert.references(row_certificate(b), cert_a)
            assert (a.related_certificate_id, b.related_certificate_id) == (b_id, a_id)
            db.session.remove()


def test_a_link_handed_over_after_a_renewed_alone_is_not_written_back(app, tmp_path, monkeypatch):
    """Newest B revoked alone: A's link goes back to the older B, unless A was renewed alone
    since the older B was found, which unlinked both."""
    from services.cert import related_pair
    from services.cert_service import CertificateService
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'handover.db'}"):
        a_id, (old_b, new_b) = _linked_rows(app, n_b=2)
        found, fired = related_pair._live_rows_linked_to, []

        def then_renewed(*args):
            rows = found(*args)
            if not fired:
                fired.append(True)
                _renew_elsewhere(app, a_id)
            return rows

        monkeypatch.setattr(related_pair, '_live_rows_linked_to', then_renewed)
        with app.app_context():
            CertificateService.revoke_certificate(new_b, reason='keyCompromise', revoke_related=False)
            monkeypatch.undo()
            db.session.expire_all()
            a, b = db.session.get(Certificate, a_id), db.session.get(Certificate, old_b)
            assert fired and a.renewed_times == 1
            assert (a.related_certificate_id, b.related_certificate_id) == (None, None)
            db.session.remove()


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_a_link_handed_over_while_a_renews_alone_waits_and_writes_nothing_on_postgresql(
        app, monkeypatch):
    from models import CA
    from services.cert.related_pair import hand_over_link
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_renewal_lock_order_pg import _race_with_an_in_place_renewal
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'renew_handover_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        a_id, (old_b, new_b) = _linked_rows(app, n_b=2)
        _revoke_elsewhere(app, new_b, 'row')
        with app.app_context():
            ca_id = CA.query.filter_by(refid=db.session.get(Certificate, a_id).caref).one().id
            db.session.remove()

        def hand_over():
            if hand_over_link(db.session.get(Certificate, new_b)) is not None:
                db.session.commit()

        blocked, errors = _race_with_an_in_place_renewal(app, url, monkeypatch, a_id, ca_id, hand_over)
        assert blocked and not errors, errors
        with app.app_context():
            a, b = db.session.get(Certificate, a_id), db.session.get(Certificate, old_b)
            assert a.renewed_times == 1
            assert (a.related_certificate_id, b.related_certificate_id) == (None, None)
            db.session.remove()


def _while_a_is_taken(app, url, a_id, b_id, work):
    """Run *work* while another session holds A locked, moving its link to *b_id* as
    link_issued does; returns whether *work* waited on that lock."""
    from tests.test_renewal_lock_order_pg import _own_session, _pid_of, _waits_on_a_lock
    holds, release, pids, errors = threading.Event(), threading.Event(), {}, []

    def take_a():
        with app.app_context():
            engine, pids['linker'] = _own_session(url)
            try:
                db.session.get(Certificate, a_id, with_for_update=True).related_certificate_id = b_id
                db.session.get(Certificate, b_id).related_certificate_id = a_id
                db.session.flush()
                holds.set()
                release.wait(30)
                db.session.commit()
            finally:
                holds.set()
                db.session.remove()
                engine.dispose()

    def run():
        with app.app_context():
            engine, pids['work'] = _own_session(url)
            try:
                work()
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
            finally:
                db.session.remove()
                engine.dispose()

    linker = threading.Thread(target=take_a)
    linker.start()
    assert holds.wait(30)
    worker = threading.Thread(target=run)
    worker.start()
    blocked = _waits_on_a_lock(url, _pid_of(pids, 'work'))
    release.set()
    worker.join(60)
    linker.join(60)
    assert not errors, errors
    return blocked


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_a_row_deleted_while_a_newer_b_takes_its_a_leaves_that_link_on_postgresql(app):
    """Deleting A's B relinks A to an older B, unless a newer B took A meanwhile."""
    from services.cert_service import CertificateService
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'renew_unlink_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        a_id, (older, gone, newer) = _linked_rows(app, n_b=3)
        with app.app_context():
            db.session.get(Certificate, a_id).related_certificate_id = gone
            db.session.get(Certificate, newer).related_certificate_id = None
            db.session.commit()
            db.session.remove()
        blocked = _while_a_is_taken(app, url, a_id, newer,
                                    lambda: CertificateService.delete_certificate(gone))
        with app.app_context():
            assert db.session.get(Certificate, gone) is None
            a, b = db.session.get(Certificate, a_id), db.session.get(Certificate, newer)
            assert blocked and (a.related_certificate_id, b.related_certificate_id) == (newer, a_id)
            assert db.session.get(Certificate, older).related_certificate_id == a_id
            db.session.remove()


def test_a_link_is_handed_over_to_the_older_b(app, tmp_path):
    from services.cert_service import CertificateService
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'handover-ok.db'}"):
        a_id, (old_b, new_b) = _linked_rows(app, n_b=2)
        with app.app_context():
            CertificateService.revoke_certificate(new_b, reason='keyCompromise', revoke_related=False)
            db.session.expire_all()
            assert db.session.get(Certificate, a_id).related_certificate_id == old_b
            db.session.remove()


def _a_member_archived_since_read(app):
    """Judging A's own link re-reads B: the caller's view of B is taken before that."""
    from services.cert.renewal import RenewalError, renew_certificate_in_place

    def archive(row_id):
        with app.app_context():
            db.session.get(Certificate, row_id).archived = True
            db.session.commit()
            db.session.remove()

    _a_id, b_id = _chain_pair(app)
    with app.app_context():
        held = db.session.get(Certificate, b_id)  # read unarchived
        thread = threading.Thread(target=archive, args=(b_id,))
        thread.start()
        thread.join(60)
        with pytest.raises(RenewalError) as e:
            renew_certificate_in_place(held, username='admin', regenerate_crl=False)
        assert e.value.status == 409 and 'renewed by another request' in e.value.message
        db.session.expire_all()
        b = db.session.get(Certificate, b_id)
        assert b.archived and not b.renewed_times
        db.session.remove()


def test_a_member_archived_since_read_is_refused_on_sqlite(app, tmp_path):
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'archived.db'}"):
        _a_member_archived_since_read(app)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_a_member_archived_since_read_is_refused_on_postgresql(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'renew_arch_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        _a_member_archived_since_read(app)
