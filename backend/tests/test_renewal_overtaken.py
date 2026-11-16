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
    if trigger == 'auto':
        assert outcome == (False, 'Certificate was renewed by another request'), outcome
    else:
        assert outcome is not None and outcome[0] == 409, outcome
        assert 'renewed by another request' in outcome[1], outcome


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
    alone renews (A is not judged revoked) but names nothing, as A's current certificate is
    not the one its extension hashed (RFC 9763 §4.1), and leaves the pair."""
    from services.cert.renewal import renew_certificate_in_place
    from utils.related_cert import read_related_certificate
    a_id, (old_b, new_b) = _linked_rows(app, n_b=2)
    with app.app_context():
        held = db.session.get(Certificate, a_id)  # kept by the session as it was read
        _renew_elsewhere(app, a_id)
        b = db.session.get(Certificate, old_b)
        outcome = renew_certificate_in_place(b, username='admin', regenerate_crl=False)
        assert outcome['related'] == [], outcome
        db.session.expire_all()
        b, a = db.session.get(Certificate, old_b), db.session.get(Certificate, a_id)
        assert b.renewed_times == 1 and held is not b
        assert read_related_certificate(_cert(b)) is None and b.related_certificate_id is None
        assert a.related_certificate_id == new_b
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


# ---- RFC 9763 §4.1: the renewed certificate names what the original's extension hashed ----

def _cert(row):
    from services.cert.related_pair import row_certificate
    return row_certificate(row)


def test_an_a_renewed_in_a_chain_names_its_own_a_not_its_b(app, tmp_path):
    """X <- A <- B with A and B linked to each other: A renewed names X, never the old B."""
    from services.cert.renewal import renew_certificate_in_place
    from tests.test_backup_cross_installation import _bound_to
    from utils.related_cert import references
    with _bound_to(app, f"sqlite:///{tmp_path / 'chain.db'}"):
        a_id, b_id = _chain_pair(app)
        with app.app_context():
            x_id = Certificate.query.filter(Certificate.related_certificate_id == a_id,
                                            Certificate.id != b_id).one().id
            cert_x, old_b = _cert(db.session.get(Certificate, x_id)), _cert(db.session.get(Certificate, b_id))
            outcome = renew_certificate_in_place(db.session.get(Certificate, a_id), username='admin',
                                                 regenerate_crl=False)
            assert [r['cert_id'] for r in outcome['related']] == [b_id], outcome
            db.session.expire_all()
            a, b = db.session.get(Certificate, a_id), db.session.get(Certificate, b_id)
            assert references(_cert(a), cert_x) and not references(_cert(a), old_b)
            assert references(_cert(b), _cert(a))
            assert (a.related_certificate_id, b.related_certificate_id) == (b_id, a_id)
            db.session.remove()


def test_an_a_renewed_alone_in_a_chain_names_its_own_a(app, tmp_path):
    """B's key not held: A renews alone and still names X, keeping its link to B."""
    from services.cert.renewal import renew_certificate_in_place
    from tests.test_backup_cross_installation import _bound_to
    from utils.related_cert import references
    with _bound_to(app, f"sqlite:///{tmp_path / 'chain_alone.db'}"):
        a_id, b_id = _chain_pair(app)
        with app.app_context():
            db.session.get(Certificate, b_id).prv = None
            db.session.commit()
            x_id = Certificate.query.filter(Certificate.related_certificate_id == a_id,
                                            Certificate.id != b_id).one().id
            cert_x, old_b = _cert(db.session.get(Certificate, x_id)), _cert(db.session.get(Certificate, b_id))
            outcome = renew_certificate_in_place(db.session.get(Certificate, a_id), username='admin',
                                                 regenerate_crl=False)
            assert outcome['related'] == [], outcome
            db.session.expire_all()
            a = db.session.get(Certificate, a_id)
            assert references(_cert(a), cert_x) and not references(_cert(a), old_b)
            assert a.related_certificate_id == b_id
            db.session.remove()


def test_the_named_a_is_found_without_reading_every_certificate(app, tmp_path):
    """Two indexed reads find X (the linked row, then the rows linked to A); no unfiltered scan."""
    from sqlalchemy import event
    from services.cert.renewal import _current_related
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'chain_cost.db'}"):
        a_id, _b_id = _chain_pair(app)
        with app.app_context():
            a = db.session.get(Certificate, a_id)
            a.crt  # loaded before counting
            statements = []

            def seen(conn, cursor, statement, *args):
                statements.append(statement)

            engine = db.session.get_bind()
            event.listen(engine, 'before_cursor_execute', seen)
            try:
                assert _current_related(a) is not None
            finally:
                event.remove(engine, 'before_cursor_execute', seen)
            on_certificates = [s for s in statements if 'FROM certificates' in s]
            assert on_certificates and all('WHERE' in s for s in on_certificates), statements
            assert len(on_certificates) == 2, on_certificates
            db.session.remove()


def test_a_malformed_extension_names_nothing(app, tmp_path):
    """An extension that cannot be read hashes no certificate: the linked row is not named."""
    import base64
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509 import UnrecognizedExtension
    from models import CA
    from services.cert.renewal import _current_related
    from services.hsm.ca_key_loader import get_ca_signing_key
    from tests.test_backup_cross_installation import _bound_to
    from utils.related_cert import RELATED_CERT_EXTENSION_OID
    with _bound_to(app, f"sqlite:///{tmp_path / 'malformed.db'}"):
        _a_id, (b_id,) = _linked_rows(app)
        with app.app_context():
            b = db.session.get(Certificate, b_id)
            assert _current_related(b) is not None
            cert_b = _cert(b)
            builder = (x509.CertificateBuilder().subject_name(cert_b.subject).issuer_name(cert_b.issuer)
                       .public_key(cert_b.public_key()).serial_number(cert_b.serial_number)
                       .not_valid_before(cert_b.not_valid_before_utc)
                       .not_valid_after(cert_b.not_valid_after_utc)
                       .add_extension(UnrecognizedExtension(RELATED_CERT_EXTENSION_OID, b'\x30\x00'),
                                      critical=False))
            ca = CA.query.filter_by(refid=b.caref).one()
            broken = builder.sign(get_ca_signing_key(ca), hashes.SHA256())
            b.crt = base64.b64encode(broken.public_bytes(serialization.Encoding.PEM)).decode()
            db.session.commit()
            assert _current_related(db.session.get(Certificate, b_id)) is None
            db.session.remove()
