"""Approval requests saved before migration 144 name their certificate in hex; the
checks against the now-decimal column must still recognise the same certificate, while
a request saved since then is read in decimal only."""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import Certificate, db
from models.policy import ApprovalRequest

# A serial with hex letters, and one whose hex spelling is all digits (ambiguous text)
SERIALS = (0xabcdef0123456789, 0x1234567890123456)
OTHER = 0x0fedcba987654321
# Saved before migration 144 ran on the test database
LEGACY = datetime(2020, 1, 1)
# A decimal recorded since 144 whose hex reading is the certificate's serial
DECIMAL = 1234567890123456


def _crt(serial):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'legacy-hex')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(serial).not_valid_before(now - timedelta(days=300))
            .not_valid_after(now + timedelta(days=10)).sign(key, hashes.SHA256()))
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


@pytest.fixture
def migrated(app):
    """Migration 144 recorded as applied now."""
    from sqlalchemy import inspect, text
    from utils.serial_format import CANONICAL_MIGRATION
    with app.app_context():
        created = '_migrations' not in inspect(db.engine).get_table_names()
        pg = db.engine.dialect.name == 'postgresql'
        if created:
            db.session.execute(text(
                "CREATE TABLE _migrations (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL UNIQUE, "
                "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)".replace(
                    'INTEGER PRIMARY KEY', 'SERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY')))
        before = db.session.execute(text("SELECT applied_at FROM _migrations WHERE name = :n"),
                                    {'n': CANONICAL_MIGRATION}).fetchall()
        db.session.execute(text("DELETE FROM _migrations WHERE name = :n"), {'n': CANONICAL_MIGRATION})
        db.session.execute(text("INSERT INTO _migrations (name, applied_at) VALUES (:n, :a)"),
                           {'n': CANONICAL_MIGRATION, 'a': datetime.now(timezone.utc).replace(tzinfo=None)})
        db.session.commit()
    yield
    with app.app_context():
        db.session.rollback()
        if created:
            db.session.execute(text("DROP TABLE _migrations"))
        else:
            db.session.execute(text("DELETE FROM _migrations WHERE name = :n"), {'n': CANONICAL_MIGRATION})
            for (applied_at,) in before:
                db.session.execute(text("INSERT INTO _migrations (name, applied_at) VALUES (:n, :a)"),
                                   {'n': CANONICAL_MIGRATION, 'a': applied_at})
        db.session.commit()


@pytest.fixture
def rows(app, migrated):
    made = {'certs': [], 'requests': []}
    with app.app_context():
        def cert(serial):
            row = Certificate(refid=str(uuid.uuid4()), descr='legacy-hex', subject_cn='legacy-hex',
                              source='manual', crt=_crt(serial), serial_number=serial)
            db.session.add(row)
            db.session.flush()
            made['certs'].append(row.id)
            return row

        def request(kind, data, status='pending', created_at=LEGACY):
            # created_at=None: saved now, after migration 144
            row = ApprovalRequest(request_type=kind, status=status, request_data=json.dumps(data),
                                  **({'created_at': created_at} if created_at else {}))
            db.session.add(row)
            db.session.flush()
            made['requests'].append(row.id)
            return row

        yield type('Rows', (), {'cert': staticmethod(cert), 'request': staticmethod(request)})
        db.session.rollback()
        ApprovalRequest.query.filter(ApprovalRequest.id.in_(made['requests'])).delete(synchronize_session=False)
        Certificate.query.filter(Certificate.id.in_(made['certs'])).delete(synchronize_session=False)
        db.session.commit()


@pytest.mark.parametrize('serial', SERIALS)
def test_revocation_request_in_hex_still_names_its_certificate(rows, serial):
    from api.v2.policies import _approval_target_gone
    cert = rows.cert(serial)
    approval = rows.request('revocation', {'certificate_id': cert.id, 'serial_number': format(serial, 'x')})
    assert _approval_target_gone(approval) is None


def test_revocation_request_for_a_replaced_certificate_is_still_refused(rows):
    from api.v2.policies import _approval_target_gone, _revoke_approved_certificate
    cert = rows.cert(SERIALS[0])
    data = {'certificate_id': cert.id, 'serial_number': format(OTHER, 'x')}
    approval = rows.request('revocation', data)
    assert 'renewed since the request' in _approval_target_gone(approval)
    with pytest.raises(ValueError, match='renewed since the request'):
        _revoke_approved_certificate(approval, data)


@pytest.mark.parametrize('serial', SERIALS)
def test_approved_revocation_in_hex_revokes(rows, serial, monkeypatch):
    import api.v2.policies as policies
    cert = rows.cert(serial)
    data = {'certificate_id': cert.id, 'serial_number': format(serial, 'x'), 'reason': 'superseded'}
    approval = rows.request('revocation', data)

    class Reached(Exception):
        pass

    def revoke(*a, **k):
        raise Reached(k.get('cert_id'))
    monkeypatch.setattr('services.cert_service.CertificateService.revoke_certificate', staticmethod(revoke))
    with pytest.raises(Reached) as hit:
        policies._revoke_approved_certificate(approval, data)
    assert hit.value.args == (cert.id,)


@pytest.mark.parametrize('serial', SERIALS)
def test_declined_renewal_in_hex_stays_declined(rows, serial):
    from services.auto_renewal_service import AutoRenewalService
    cert = rows.cert(serial)
    rows.request('renewal', {'certificate_id': cert.id, 'trigger': 'auto', 'serial_number': format(serial, 'x')},
                 status='rejected')
    assert AutoRenewalService._declined(cert) is True


def test_declined_renewal_of_a_replaced_certificate_is_not_declined(rows):
    from services.auto_renewal_service import AutoRenewalService
    cert = rows.cert(SERIALS[0])
    rows.request('renewal', {'certificate_id': cert.id, 'trigger': 'auto', 'serial_number': format(OTHER, 'x')},
                 status='rejected')
    assert AutoRenewalService._declined(cert) is False


def test_a_decimal_saved_since_144_is_not_read_as_hex(rows):
    from api.v2.policies import _approval_target_gone, _revoke_approved_certificate
    from services.auto_renewal_service import AutoRenewalService
    cert = rows.cert(int(str(DECIMAL), 16))
    data = {'certificate_id': cert.id, 'serial_number': str(DECIMAL), 'reason': 'superseded'}
    approval = rows.request('revocation', data, created_at=None)
    assert 'renewed since the request' in _approval_target_gone(approval)
    with pytest.raises(ValueError, match='renewed since the request'):
        _revoke_approved_certificate(approval, data)
    rows.request('renewal', {'certificate_id': cert.id, 'trigger': 'auto', 'serial_number': str(DECIMAL)},
                 status='rejected', created_at=None)
    assert AutoRenewalService._declined(cert) is False


def test_the_same_text_saved_before_144_names_the_certificate(rows):
    from api.v2.policies import _approval_target_gone
    cert = rows.cert(int(str(DECIMAL), 16))
    approval = rows.request('revocation', {'certificate_id': cert.id, 'serial_number': str(DECIMAL)})
    assert _approval_target_gone(approval) is None


def test_a_decimal_saved_since_144_names_its_certificate(rows):
    from api.v2.policies import _approval_target_gone
    cert = rows.cert(DECIMAL)
    approval = rows.request('revocation', {'certificate_id': cert.id, 'serial_number': str(DECIMAL)},
                            created_at=None)
    assert _approval_target_gone(approval) is None


def test_without_the_migration_date_the_hex_reading_still_counts(app):
    from utils.serial_format import recorded_before_canonical
    from utils.datetime_utils import utc_now
    with app.app_context():
        assert recorded_before_canonical(None) is True
        if '_migrations' not in __import__('sqlalchemy').inspect(db.engine).get_table_names():
            assert recorded_before_canonical(utc_now()) is True


def test_the_migration_date_is_read_in_utc(app, migrated):
    from sqlalchemy import text
    from utils.serial_format import CANONICAL_MIGRATION, recorded_before_canonical
    from utils.datetime_utils import utc_now
    with app.app_context():
        if db.engine.dialect.name == 'postgresql':
            # One transaction: the row is written as the runner writes it, and read back in a zone far from UTC
            from migration_runner import _PG_NOW_UTC
            db.session.execute(text("SET LOCAL TIME ZONE 'Pacific/Kiritimati'"))
            db.session.execute(text("DELETE FROM _migrations WHERE name = :n"), {'n': CANONICAL_MIGRATION})
            db.session.execute(text(f"INSERT INTO _migrations (name, applied_at) VALUES (:n, {_PG_NOW_UTC})"),
                               {'n': CANONICAL_MIGRATION})
        assert recorded_before_canonical(utc_now() - timedelta(minutes=5)) is True
        assert recorded_before_canonical(utc_now() + timedelta(minutes=5)) is False
        db.session.rollback()


def test_an_unreadable_migration_date_allows_the_hex_reading(app, migrated):
    from sqlalchemy import text
    from utils.serial_format import CANONICAL_MIGRATION, recorded_before_canonical
    from utils.datetime_utils import utc_now
    with app.app_context():
        if db.engine.dialect.name != 'sqlite':
            pytest.skip('only SQLite stores the date as free text')
        db.session.execute(text("UPDATE _migrations SET applied_at = 'not a date' WHERE name = :n"),
                           {'n': CANONICAL_MIGRATION})
        assert recorded_before_canonical(utc_now()) is True
        db.session.rollback()
