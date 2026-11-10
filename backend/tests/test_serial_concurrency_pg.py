"""Issuance under one CA from many workers: distinct serials, no lost count.

The certificate serial is random (RFC 5280 §4.1.2.2); ``ca.serial`` counts the
certificates a CA issued and is incremented in the database, so two workers on
two nodes never overwrite each other's count.
"""
import os
import threading
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db
from tests.test_crl_number_monotonic import _authority, _ca_row

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
WORKERS, EACH = 4, 25


def _csr(name):
    key = ec.generate_private_key(ec.SECP256R1())
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            .sign(key, hashes.SHA256()))


def _issue(ca_id, name):
    from services.ca import CAService
    ca = db.session.get(CA, ca_id)
    return CAService.sign_csr_from_crypto(ca, _csr(name), validity_days=30, source='test')


def test_next_ca_serial_counts_in_the_database(app):
    from utils.ca_serial_counter import next_ca_serial
    with app.app_context():
        ca = _ca_row(*_authority())
        assert [next_ca_serial(ca), next_ca_serial(ca)] == [1, 2]
        assert ca.serial == 2 and 'serial' not in db.inspect(ca).committed_state
        db.session.commit()
        db.session.expire_all()
        assert db.session.get(CA, ca.id).serial == 2


def test_issuance_counts_one_per_certificate_on_sqlite(app):
    with app.app_context():
        ca_id = _ca_row(*_authority()).id
        for i in range(3):
            _issue(ca_id, f'sqlite-{i}.example.test')
        db.session.expire_all()
        assert db.session.get(CA, ca_id).serial == 3



def test_a_taken_random_serial_is_signed_again_once(app):
    """RFC 5280 §4.1.2.2: the second certificate cannot reuse a serial; one retry, then a clean failure."""
    from unittest.mock import patch
    from sqlalchemy.exc import IntegrityError
    taken = x509.random_serial_number()
    with app.app_context():
        ca_id = _ca_row(*_authority()).id
        with patch('cryptography.x509.random_serial_number', return_value=taken):
            _issue(ca_id, 'first.example.test')
        fresh = x509.random_serial_number()
        with patch('cryptography.x509.random_serial_number', side_effect=[taken, fresh]):
            _, second = _issue(ca_id, 'second.example.test')
        assert int(second, 16) == fresh
        with patch('cryptography.x509.random_serial_number', return_value=taken), \
                pytest.raises(IntegrityError):
            _issue(ca_id, 'third.example.test')
        db.session.expire_all()
        assert db.session.get(CA, ca_id).serial == 2

def _stale(ca):
    from sqlalchemy.orm.attributes import set_committed_value
    set_committed_value(ca, 'serial', 0)  # what this worker read before another one issued


def _by_create_certificate(ca):
    from services.cert_service import CertificateService
    CertificateService.create_certificate(
        descr='stale count', caref=ca.refid, dn={'CN': 'stale-create.example.test'},
        key_type='secp256r1', validity_days=30)


def _by_sign_csr(ca):
    from services.cert_service import CertificateService
    csr_row = CertificateService.generate_csr(
        descr='stale count csr', dn={'CN': 'stale-csr.example.test'}, key_type='2048')
    db.session.commit()
    _stale(ca)  # the commit reloaded the CA row
    CertificateService.sign_csr(cert_id=csr_row.id, caref=ca.refid, validity_days=30)


def _by_sign_csr_from_crypto(ca):
    _issue(ca.id, 'stale-crypto.example.test')


def _by_intermediate(ca):
    from services.ca import CAService
    CAService.create_internal_ca(descr='stale count sub', dn={'CN': 'stale count sub'},
                                 key_type='secp256r1', caref=ca.refid, validity_days=365)


def _by_increment_serial(ca):
    from services.ca import CAService
    CAService.increment_serial(ca.id)


@pytest.mark.parametrize('issue', [_by_create_certificate, _by_sign_csr, _by_sign_csr_from_crypto,
                                   _by_intermediate, _by_increment_serial])
def test_every_site_counts_from_the_database_not_from_a_stale_row(app, create_ca, issue):
    """Another worker counted meanwhile: the site adds one to the stored count, not to its copy."""
    ca_id = create_ca(cn=f'Stale count {issue.__name__}')['id']
    with app.app_context():
        db.session.execute(CA.__table__.update().where(CA.__table__.c.id == ca_id).values(serial=10))
        db.session.commit()
        ca = db.session.get(CA, ca_id)
        _stale(ca)
        issue(ca)
        db.session.commit()
        db.session.expire_all()
        assert db.session.get(CA, ca_id).serial == 11


def _race(app, ca_id):
    errors, start = [], threading.Barrier(WORKERS)

    def worker(n):
        try:
            with app.app_context():
                start.wait(10)
                for i in range(EACH):
                    _issue(ca_id, f'w{n}-{i}.example.test')
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
    return errors


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_concurrent_issuance_on_postgresql_keeps_serials_and_count(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    schema = f'serial_race_{uuid.uuid4().hex[:6]}'
    with _a_schema_of_our_own(schema) as url, _bound_to(app, url, is_postgresql=True):
        with app.app_context():
            ca = _ca_row(*_authority())
            ca_id, caref = ca.id, ca.refid
            db.session.remove()
        errors = _race(app, ca_id)
        with app.app_context():
            serials = [s for (s,) in db.session.query(Certificate.serial_number)
                       .filter_by(caref=caref)]
            count = db.session.get(CA, ca_id).serial
            db.session.remove()
    assert errors == []
    assert len(serials) == len(set(serials)) == WORKERS * EACH
    assert count == WORKERS * EACH
