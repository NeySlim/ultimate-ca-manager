"""Persistent revocation records on the CRL and over OCSP, and the opt-in purges.

Every CRL here is really generated and parsed, every OCSP answer is a real
response from the /ocsp endpoint. The scenarios run on SQLite and, when
UCM_TEST_PG_URL is set, on PostgreSQL.
"""
import base64
import contextlib
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import ocsp
from cryptography.x509.oid import CRLEntryExtensionOID, NameOID
from sqlalchemy import create_engine, text

from models import db, CA, Certificate, RevokedSerial, SystemConfig
from services.crl.query import CRLQueryMixin
from services.crl_service import CRLService
from services.ocsp_service import OCSPService

_PG_URL = os.environ.get('UCM_TEST_PG_URL')

# Hex spelling carries letters, so lower and upper hex differ from decimal
SERIAL_A = 0xABCDEF0123
SERIAL_B = 0xABCDEF0456
SERIAL_C = 0xABCDEF0789


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _key():
    return ec.generate_private_key(ec.SECP256R1())


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------

def _empty_pg_schema():
    engine = create_engine(_PG_URL, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(text('DROP SCHEMA public CASCADE'))
            connection.execute(text('CREATE SCHEMA public'))
    finally:
        engine.dispose()


@contextlib.contextmanager
def _on_postgresql(app):
    """The application bound to the shared PostgreSQL bench, then put back."""
    from services.database_admin.helpers import _force_register_all_models
    from services.database_admin.migration import _create_target_schema
    from tests.conftest import pg_bench_exclusive

    with pg_bench_exclusive():
        _empty_pg_schema()
        _force_register_all_models()
        engine = create_engine(_PG_URL, pool_pre_ping=True)
        _create_target_schema(engine, True)
        engines = db._app_engines[app]
        original = engines[None]
        with app.app_context():
            engines[None] = engine
            db.session.remove()
        try:
            yield
        finally:
            with app.app_context():
                engines[None] = original
                db.session.remove()
            engine.dispose()
            _empty_pg_schema()


@pytest.fixture(params=[
    'sqlite',
    pytest.param('postgresql', marks=pytest.mark.postgres),
])
def backend(request, app):
    if request.param == 'postgresql':
        if not _PG_URL:
            pytest.skip('UCM_TEST_PG_URL not set; skipping the PostgreSQL target')
        with _on_postgresql(app), app.app_context():
            assert db.engine.dialect.name == 'postgresql'
            yield 'postgresql'
    else:
        with app.app_context():
            yield 'sqlite'


# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------

def _make_ca(*, delta=False):
    tag = uuid.uuid4().hex[:10]
    ca_key = _key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'B6 CA {tag}')])
    now = datetime.now(timezone.utc)
    ca_cert = (x509.CertificateBuilder()
               .subject_name(name).issuer_name(name)
               .public_key(ca_key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(days=1))
               .not_valid_after(now + timedelta(days=365))
               .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
                              critical=False)
               .sign(ca_key, hashes.SHA256()))
    ca = CA(refid=f'b6-ca-{tag}', descr=f'B6 CA {tag}', serial=0,
            prv=base64.b64encode(ca_key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption())).decode(),
            crt=base64.b64encode(ca_cert.public_bytes(serialization.Encoding.PEM)).decode(),
            subject=name.rfc4514_string(), issuer=name.rfc4514_string(),
            ocsp_enabled=True, cdp_enabled=True, delta_crl_enabled=delta)
    db.session.add(ca)
    db.session.commit()
    _CREATED_CA_REFIDS.append(ca.refid)
    return ca, ca_key, ca_cert


def _issue(ca_key, ca_cert, serial):
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'leaf-{serial}')]))
            .issuer_name(ca_cert.subject)
            .public_key(_key().public_key())
            .serial_number(serial)
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=90))
            .sign(ca_key, hashes.SHA256()))


def _store(ca, leaf, column=None, *, revoked=False, reason='keyCompromise',
           valid_to='default', revoked_at=None):
    now = _now()
    row = Certificate(
        refid=f'b6-cert-{uuid.uuid4().hex[:10]}', descr='b6', caref=ca.refid,
        crt=base64.b64encode(leaf.public_bytes(serialization.Encoding.PEM)).decode(),
        serial_number=column if column is not None else str(leaf.serial_number),
        subject=leaf.subject.rfc4514_string(), issuer=leaf.issuer.rfc4514_string(),
        revoked=revoked,
        revoked_at=(revoked_at or now) if revoked else None,
        revoke_reason=reason if revoked else None,
        valid_from=now - timedelta(days=1),
        valid_to=now + timedelta(days=90) if valid_to == 'default' else valid_to,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _persist(ca, column, *, reason='keyCompromise', valid_to=None, revoked_at=None,
             certificate_id=None):
    row = RevokedSerial(caref=ca.refid, serial_number=column,
                        revoked_at=revoked_at or _now(), revoke_reason=reason,
                        valid_to=valid_to or _now() + timedelta(days=90),
                        certificate_id=certificate_id)
    db.session.add(row)
    db.session.commit()
    return row


def _setting(key, value):
    SystemConfig.query.filter_by(key=key).delete()
    if value is not None:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


_FLAGS = ('crl_auto_delete_expired_revoked', 'crl_auto_purge_stale_serials')
# CAs this module created on the shared database, removed after each test
_CREATED_CA_REFIDS = []


def _delete_rows_of(ca_refids):
    """Every row tied to these CAs or to their certificates, then the CAs."""
    cas = CA.query.filter(CA.refid.in_(ca_refids)).all()
    if not cas:
        return
    ca_keys = {'id': [c.id for c in cas], 'refid': [c.refid for c in cas]}
    certs = Certificate.query.filter(Certificate.caref.in_(ca_keys['refid'])).all()
    cert_keys = {'id': [c.id for c in certs], 'refid': [c.refid for c in certs]}
    targets = {'certificates': cert_keys, 'certificate_authorities': ca_keys}
    for table in reversed(db.metadata.sorted_tables):
        for fk in table.foreign_keys:
            keys = targets.get(fk.column.table.name, {}).get(fk.column.name)
            if keys and table.name not in targets:
                db.session.execute(table.delete().where(fk.parent.in_(keys)))
    # Rows linked without a foreign key
    RevokedSerial.query.filter(RevokedSerial.caref.in_(ca_keys['refid'])).delete(
        synchronize_session=False)
    Certificate.query.filter(Certificate.id.in_(cert_keys['id'])).delete(
        synchronize_session=False)
    CA.query.filter(CA.id.in_(ca_keys['id'])).delete(synchronize_session=False)
    db.session.commit()


@pytest.fixture(autouse=True)
def isolated_state(app):
    """Purge flags off during each test, then put back as they were, and every
    row the test created removed, whether the test passed or not."""
    with app.app_context():
        saved = {k: (row.value if row else None) for k in _FLAGS
                 for row in [SystemConfig.query.filter_by(key=k).first()]}
        for key in _FLAGS:
            _setting(key, None)
    _CREATED_CA_REFIDS.clear()
    try:
        yield
    finally:
        with app.app_context():
            db.session.rollback()
            try:
                _delete_rows_of(list(_CREATED_CA_REFIDS))
            finally:
                db.session.rollback()
                for key, value in saved.items():
                    _setting(key, value)
                _CREATED_CA_REFIDS.clear()


def _full_crl(ca):
    meta = CRLService.generate_crl(ca.id)
    return x509.load_pem_x509_crl(meta.crl_pem.encode())


def _entries(crl):
    return {e.serial_number: e for e in crl}


def _reason(entry):
    try:
        return entry.extensions.get_extension_for_oid(CRLEntryExtensionOID.CRL_REASON).value.reason
    except x509.ExtensionNotFound:
        return None


def _ocsp(app, ca_cert, leaf):
    """A real OCSP request through /ocsp: (status, reason)."""
    req = ocsp.OCSPRequestBuilder().add_certificate(leaf, ca_cert, hashes.SHA1()).build()
    with app.test_client() as client:
        r = client.post('/ocsp', data=req.public_bytes(serialization.Encoding.DER),
                        content_type='application/ocsp-request')
    assert r.status_code == 200, r.data
    resp = ocsp.load_der_ocsp_response(r.data)
    assert resp.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
    assert resp.serial_number == leaf.serial_number
    status = resp.certificate_status
    reason = resp.revocation_reason if status == ocsp.OCSPCertStatus.REVOKED else None
    return status, reason


# --------------------------------------------------------------------------
# Full CRL
# --------------------------------------------------------------------------

class TestFullCrl:

    def test_a_deleted_certificate_stays_listed_until_its_expiry(self, backend):
        """Scenario 1: revoked then deleted, the serial is still published."""
        ca, ca_key, ca_cert = _make_ca()
        leaf = _issue(ca_key, ca_cert, SERIAL_A)
        row = _store(ca, leaf, revoked=True)
        _persist(ca, row.serial_number, certificate_id=row.id)
        db.session.delete(row)
        db.session.commit()

        entries = _entries(_full_crl(ca))
        assert set(entries) == {SERIAL_A}
        assert _reason(entries[SERIAL_A]) == x509.ReasonFlags.key_compromise

    def test_an_expired_record_is_left_off(self, backend):
        ca, _, _ = _make_ca()
        _persist(ca, str(SERIAL_A), valid_to=_now() - timedelta(minutes=1))
        _persist(ca, str(SERIAL_B))
        assert set(_entries(_full_crl(ca))) == {SERIAL_B}

    def test_two_renewals_list_the_two_replaced_serials(self, backend):
        """Scenario 2: three serials, the two replaced ones are superseded on
        the CRL, the current one is absent."""
        ca, ca_key, ca_cert = _make_ca()
        current = _store(ca, _issue(ca_key, ca_cert, SERIAL_C), format(SERIAL_C, 'x'))
        _persist(ca, format(SERIAL_A, 'x'), reason='superseded', certificate_id=current.id,
                 revoked_at=_now() - timedelta(days=2))
        _persist(ca, format(SERIAL_B, 'x'), reason='superseded', certificate_id=current.id,
                 revoked_at=_now() - timedelta(days=1))

        entries = _entries(_full_crl(ca))
        assert set(entries) == {SERIAL_A, SERIAL_B}
        assert all(_reason(e) == x509.ReasonFlags.superseded for e in entries.values())

    def test_a_record_its_unrevoked_certificate_still_carries_is_dropped(self, backend):
        """A lifted revocation the record outlived: the certificate still holds
        the serial and is valid, so the CRL must not list it."""
        ca, ca_key, ca_cert = _make_ca()
        row = _store(ca, _issue(ca_key, ca_cert, SERIAL_A), str(SERIAL_A))
        _persist(ca, format(SERIAL_A, 'X'), reason='certificateHold', certificate_id=row.id)
        assert set(_entries(_full_crl(ca))) == set()

    def test_the_live_record_wins_over_the_persistent_one(self, backend):
        ca, ca_key, ca_cert = _make_ca()
        row = _store(ca, _issue(ca_key, ca_cert, SERIAL_A), format(SERIAL_A, 'x'),
                     revoked=True, reason='cACompromise')
        _persist(ca, str(SERIAL_A), reason='superseded', certificate_id=row.id)
        entries = _entries(_full_crl(ca))
        assert list(entries) == [SERIAL_A]
        assert _reason(entries[SERIAL_A]) == x509.ReasonFlags.ca_compromise

    def test_two_records_of_one_serial_make_one_entry(self, backend):
        ca, _, _ = _make_ca()
        _persist(ca, format(SERIAL_A, 'X'), revoked_at=_now() - timedelta(days=3))
        _persist(ca, str(SERIAL_A), revoked_at=_now() - timedelta(days=1))
        _persist(ca, str(SERIAL_A), revoked_at=_now())
        crl = _full_crl(ca)
        assert [e.serial_number for e in crl] == [SERIAL_A]

    def test_two_certificate_rows_of_one_serial_make_one_entry(self, backend):
        """Scenario 5: same serial, hex row and decimal row."""
        ca, ca_key, ca_cert = _make_ca()
        leaf = _issue(ca_key, ca_cert, SERIAL_A)
        _store(ca, leaf, format(SERIAL_A, 'x'), revoked=True)
        _store(ca, leaf, str(SERIAL_A), revoked=True, reason='superseded')
        crl = _full_crl(ca)
        assert [e.serial_number for e in crl] == [SERIAL_A]
        # Deterministic: the first row wins
        assert _reason(crl[0]) == x509.ReasonFlags.key_compromise

    def test_a_revoked_certificate_without_expiry_is_listed(self, backend):
        """Scenario 10."""
        ca, ca_key, ca_cert = _make_ca()
        _store(ca, _issue(ca_key, ca_cert, SERIAL_A), revoked=True, valid_to=None)
        assert set(_entries(_full_crl(ca))) == {SERIAL_A}

    def test_another_cas_records_stay_off(self, backend):
        ca, _, _ = _make_ca()
        other, _, _ = _make_ca()
        _persist(other, str(SERIAL_A))
        assert set(_entries(_full_crl(ca))) == set()

    def test_an_absent_ca_is_refused(self, backend):
        with pytest.raises(ValueError):
            CRLQueryMixin.get_revoked_certificates(987654321)


# --------------------------------------------------------------------------
# Delta CRL
# --------------------------------------------------------------------------

class TestDeltaCrl:

    def test_a_serial_replaced_after_the_base_is_on_the_delta(self, backend):
        """Scenario 7."""
        ca, ca_key, ca_cert = _make_ca(delta=True)
        base = CRLService.generate_crl(ca.id)
        current = _store(ca, _issue(ca_key, ca_cert, SERIAL_B))
        _persist(ca, str(SERIAL_A), reason='superseded', certificate_id=current.id,
                 revoked_at=base.this_update + timedelta(seconds=1))
        # Revoked before the base: on the base already, not repeated
        _persist(ca, str(SERIAL_C), revoked_at=base.this_update - timedelta(hours=1))

        meta = CRLService.generate_delta_crl(ca.id)
        delta = x509.load_pem_x509_crl(meta.crl_pem.encode())
        entries = _entries(delta)
        assert set(entries) == {SERIAL_A}
        assert _reason(entries[SERIAL_A]) == x509.ReasonFlags.superseded

    def test_the_delta_lists_a_serial_once(self, backend):
        ca, ca_key, ca_cert = _make_ca(delta=True)
        base = CRLService.generate_crl(ca.id)
        later = base.this_update + timedelta(seconds=1)
        row = _store(ca, _issue(ca_key, ca_cert, SERIAL_A), format(SERIAL_A, 'x'),
                     revoked=True, revoked_at=later)
        _persist(ca, str(SERIAL_A), certificate_id=row.id, revoked_at=later)
        _persist(ca, format(SERIAL_B, 'X'), revoked_at=later)
        _persist(ca, str(SERIAL_B), revoked_at=later)
        _persist(ca, str(SERIAL_C), revoked_at=later, valid_to=_now() - timedelta(minutes=1))

        meta = CRLService.generate_delta_crl(ca.id)
        serials = [e.serial_number for e in x509.load_pem_x509_crl(meta.crl_pem.encode())]
        assert sorted(serials) == [SERIAL_A, SERIAL_B]


# --------------------------------------------------------------------------
# OCSP
# --------------------------------------------------------------------------

class TestOcsp:

    def test_a_deleted_certificate_answers_revoked_even_after_its_expiry(self, app, backend):
        """Scenario 4: the record is consulted without looking at valid_to."""
        ca, ca_key, ca_cert = _make_ca()
        leaf = _issue(ca_key, ca_cert, SERIAL_A)
        _persist(ca, str(SERIAL_A), reason='keyCompromise',
                 valid_to=_now() - timedelta(days=1))
        status, reason = _ocsp(app, ca_cert, leaf)
        assert status == ocsp.OCSPCertStatus.REVOKED
        assert reason == x509.ReasonFlags.key_compromise

    @pytest.mark.parametrize('spelling', [str, lambda n: format(n, 'x'), lambda n: format(n, 'X')],
                             ids=['decimal', 'lower-hex', 'upper-hex'])
    def test_every_spelling_of_a_record_is_found(self, app, backend, spelling):
        """Scenario 9, on the persistent record."""
        ca, ca_key, ca_cert = _make_ca()
        leaf = _issue(ca_key, ca_cert, SERIAL_A)
        _persist(ca, spelling(SERIAL_A), reason='superseded')
        assert _ocsp(app, ca_cert, leaf) == (ocsp.OCSPCertStatus.REVOKED,
                                             x509.ReasonFlags.superseded)

    @pytest.mark.parametrize('spelling', [str, lambda n: format(n, 'x'), lambda n: format(n, 'X')],
                             ids=['decimal', 'lower-hex', 'upper-hex'])
    def test_every_spelling_of_a_certificate_is_found(self, app, backend, spelling):
        """Scenario 9, on the certificate row."""
        ca, ca_key, ca_cert = _make_ca()
        good = _issue(ca_key, ca_cert, SERIAL_A)
        _store(ca, good, spelling(SERIAL_A))
        revoked = _issue(ca_key, ca_cert, SERIAL_B)
        _store(ca, revoked, spelling(SERIAL_B), revoked=True, reason='affiliationChanged')
        assert _ocsp(app, ca_cert, good) == (ocsp.OCSPCertStatus.GOOD, None)
        assert _ocsp(app, ca_cert, revoked) == (ocsp.OCSPCertStatus.REVOKED,
                                                x509.ReasonFlags.affiliation_changed)

    def test_a_revoked_duplicate_is_never_hidden(self, app, backend):
        """Two rows hold the serial, one revoked: the CRL lists it, so the
        responder answers revoked too."""
        ca, ca_key, ca_cert = _make_ca()
        leaf = _issue(ca_key, ca_cert, SERIAL_A)
        _store(ca, leaf, str(SERIAL_A))
        _store(ca, leaf, format(SERIAL_A, 'x'), revoked=True)
        assert SERIAL_A in _entries(_full_crl(ca))
        assert _ocsp(app, ca_cert, leaf)[0] == ocsp.OCSPCertStatus.REVOKED

    def test_a_live_valid_certificate_wins_over_a_record(self, app, backend):
        ca, ca_key, ca_cert = _make_ca()
        leaf = _issue(ca_key, ca_cert, SERIAL_A)
        _store(ca, leaf, str(SERIAL_A))
        _persist(ca, format(SERIAL_A, 'x'))
        assert _ocsp(app, ca_cert, leaf) == (ocsp.OCSPCertStatus.GOOD, None)

    @pytest.mark.parametrize('stored,expected', [
        ('cACompromise', x509.ReasonFlags.ca_compromise),
        (None, x509.ReasonFlags.unspecified),
        ('bogus', x509.ReasonFlags.unspecified),
        ('removeFromCRL', x509.ReasonFlags.unspecified),
    ])
    def test_the_record_reason_is_mapped(self, backend, stored, expected):
        ca, _, _ = _make_ca()
        revoked_at = _now() - timedelta(hours=2)
        _persist(ca, str(SERIAL_A), reason=stored, revoked_at=revoked_at)
        found = OCSPService._persisted_revocation(ca, OCSPService._serial_spellings(SERIAL_A))
        assert found is not None
        assert found[1] == expected
        assert abs((found[0] - revoked_at).total_seconds()) < 1

    def test_no_record_and_no_row_is_unknown(self, app, backend):
        ca, ca_key, ca_cert = _make_ca()
        other, _, _ = _make_ca()
        _persist(other, str(SERIAL_A))
        leaf = _issue(ca_key, ca_cert, SERIAL_A)
        assert OCSPService._persisted_revocation(ca, OCSPService._serial_spellings(SERIAL_A)) is None
        assert _ocsp(app, ca_cert, leaf)[0] == ocsp.OCSPCertStatus.UNKNOWN

    def test_the_spellings(self):
        assert set(OCSPService._serial_spellings(0xAB0)) == {'2736', 'ab0', 'AB0'}


# --------------------------------------------------------------------------
# Settings and purges
# --------------------------------------------------------------------------

class TestSettings:

    @pytest.mark.parametrize('key,method', [
        ('crl_auto_delete_expired_revoked', 'is_auto_delete_enabled'),
        ('crl_auto_purge_stale_serials', 'is_purge_stale_serials_enabled'),
    ])
    def test_reading(self, app, key, method):
        """Scenario 8."""
        with app.app_context():
            for stored, expected in (('TRUE', True), ('1', True), ('yes', True), ('on', True),
                                     (' On ', True), ('false', False), ('', False),
                                     ('maybe', False), (None, False)):
                _setting(key, stored)
                assert getattr(CRLQueryMixin, method)() is expected, stored


class TestPurges:

    def test_stale_records_stay_by_default_and_go_when_enabled(self, backend):
        """Scenario 3."""
        ca, _, _ = _make_ca()
        other, _, _ = _make_ca()
        stale = _persist(ca, str(SERIAL_A), valid_to=_now() - timedelta(minutes=1))
        fresh = _persist(ca, str(SERIAL_B))
        foreign = _persist(other, str(SERIAL_C), valid_to=_now() - timedelta(minutes=1))
        stale_id, fresh_id, foreign_id = stale.id, fresh.id, foreign.id

        _full_crl(ca)
        assert db.session.get(RevokedSerial, stale_id) is not None

        _setting('crl_auto_purge_stale_serials', 'true')
        assert set(_entries(_full_crl(ca))) == {SERIAL_B}
        db.session.expire_all()
        assert db.session.get(RevokedSerial, stale_id) is None
        assert db.session.get(RevokedSerial, fresh_id) is not None
        assert db.session.get(RevokedSerial, foreign_id) is not None

    def test_purge_counts_and_absent_ca(self, backend):
        ca, _, _ = _make_ca()
        _persist(ca, str(SERIAL_A), valid_to=_now() - timedelta(days=1))
        _persist(ca, str(SERIAL_B), valid_to=_now() - timedelta(days=2))
        _persist(ca, str(SERIAL_C))
        assert CRLQueryMixin.purge_stale_revoked_serials(ca.id) == 2
        assert CRLQueryMixin.purge_stale_revoked_serials(ca.id) == 0
        assert CRLQueryMixin.purge_stale_revoked_serials(987654321) == 0
        assert CRLQueryMixin.purge_expired_revoked_certificates(987654321) == 0

    def test_a_failed_purge_commit_is_rolled_back(self, backend, monkeypatch):
        ca, _, _ = _make_ca()
        row = _persist(ca, str(SERIAL_A), valid_to=_now() - timedelta(days=1))
        row_id = row.id

        def _boom():
            raise RuntimeError('commit refused')
        monkeypatch.setattr(db.session, 'commit', _boom)
        assert CRLQueryMixin.purge_stale_revoked_serials(ca.id) == 0
        monkeypatch.undo()
        db.session.expire_all()
        assert db.session.get(RevokedSerial, row_id) is not None

    def test_expired_revoked_certificates_are_selected(self, backend, monkeypatch):
        """Only revoked rows of this CA with a passed valid_to; one failure
        does not stop the loop."""
        from services.cert.service import CertificateService
        ca, ca_key, ca_cert = _make_ca()
        other, o_key, o_cert = _make_ca()
        past = _now() - timedelta(days=1)
        doomed = _store(ca, _issue(ca_key, ca_cert, SERIAL_A), revoked=True, valid_to=past)
        failing = _store(ca, _issue(ca_key, ca_cert, SERIAL_B), revoked=True, valid_to=past)
        doomed2 = _store(ca, _issue(ca_key, ca_cert, SERIAL_C), revoked=True, valid_to=past)
        _store(ca, _issue(ca_key, ca_cert, 0x111), revoked=True, valid_to=None)
        _store(ca, _issue(ca_key, ca_cert, 0x222), revoked=False, valid_to=past)
        _store(ca, _issue(ca_key, ca_cert, 0x333), revoked=True)
        _store(other, _issue(o_key, o_cert, 0x444), revoked=True, valid_to=past)
        calls = []

        def _delete(cert_id, username='system'):
            calls.append((cert_id, username))
            if cert_id == failing.id:
                raise RuntimeError('blocked')
            return True
        monkeypatch.setattr(CertificateService, 'delete_certificate', staticmethod(_delete))

        assert CRLQueryMixin.purge_expired_revoked_certificates(ca.id) == 2
        assert sorted(calls) == sorted([(doomed.id, 'system'), (failing.id, 'system'),
                                        (doomed2.id, 'system')])

    def test_the_delete_flag_drives_the_purge_at_generation(self, backend, monkeypatch):
        from services.cert.service import CertificateService
        ca, ca_key, ca_cert = _make_ca()
        _store(ca, _issue(ca_key, ca_cert, SERIAL_A), revoked=True,
               valid_to=_now() - timedelta(days=1))
        calls = []
        monkeypatch.setattr(CertificateService, 'delete_certificate',
                            staticmethod(lambda cert_id, username='system': calls.append(cert_id) or True))
        _full_crl(ca)
        assert calls == []
        _setting('crl_auto_delete_expired_revoked', 'on')
        _full_crl(ca)
        assert len(calls) == 1

    def test_a_failing_housekeeping_does_not_block_the_crl(self, backend, monkeypatch):
        ca, ca_key, ca_cert = _make_ca()
        _store(ca, _issue(ca_key, ca_cert, SERIAL_A), revoked=True)
        _setting('crl_auto_purge_stale_serials', 'true')
        _setting('crl_auto_delete_expired_revoked', 'true')

        def _boom(_ca_id):
            raise RuntimeError('purge exploded')
        monkeypatch.setattr(CRLQueryMixin, 'purge_stale_revoked_serials', staticmethod(_boom))
        monkeypatch.setattr(CRLQueryMixin, 'purge_expired_revoked_certificates',
                            staticmethod(_boom))
        assert set(_entries(_full_crl(ca))) == {SERIAL_A}

    def test_a_failing_first_purge_does_not_skip_the_second(self, backend, monkeypatch):
        ca, ca_key, ca_cert = _make_ca()
        _store(ca, _issue(ca_key, ca_cert, SERIAL_A), revoked=True)
        _setting('crl_auto_purge_stale_serials', 'true')
        _setting('crl_auto_delete_expired_revoked', 'true')
        calls = []

        def _boom(_ca_id):
            raise RuntimeError('stale purge exploded')
        monkeypatch.setattr(CRLQueryMixin, 'purge_stale_revoked_serials', staticmethod(_boom))
        monkeypatch.setattr(CRLQueryMixin, 'purge_expired_revoked_certificates',
                            staticmethod(lambda ca_id: calls.append(ca_id) or 0))
        assert set(_entries(_full_crl(ca))) == {SERIAL_A}
        assert calls == [ca.id]


class TestAutoDeleteEndToEnd:

    def test_an_expired_revoked_certificate_is_deleted_and_its_record_kept(
            self, app, create_ca, create_cert, monkeypatch):
        """Scenario 6. Runs the deletion service of sub-lot B.4 when present;
        until then a stand-in applies its contract (row and file gone, record
        kept with ``certificate_id`` set to NULL)."""
        from services.cert.service import CertificateService
        from utils.file_naming import cert_cert_path, cert_key_path
        real_delete = CertificateService.delete_certificate

        def _delete(cert_id, username='system'):
            try:
                return real_delete(cert_id, username=username)
            except NotImplementedError:
                db.session.rollback()
            row = db.session.get(Certificate, cert_id)
            for path in (cert_cert_path(row), cert_key_path(row)):
                if os.path.exists(path):
                    os.unlink(path)
            RevokedSerial.query.filter_by(certificate_id=cert_id).update(
                {'certificate_id': None}, synchronize_session=False)
            db.session.delete(row)
            db.session.commit()
            return True
        monkeypatch.setattr(CertificateService, 'delete_certificate', staticmethod(_delete))

        ca = create_ca(cn=f'B6 Auto Delete {uuid.uuid4().hex[:6]}')
        with app.app_context():
            _CREATED_CA_REFIDS.append(db.session.get(CA, ca['id']).refid)
        cert = create_cert(ca_id=ca['id'])
        with app.app_context():
            row = db.session.get(Certificate, cert['id'])
            path = cert_cert_path(row)
            assert os.path.exists(path)
            ca_row = db.session.get(CA, ca['id'])
            serial = row.serial_number
            row.revoked = True
            row.revoked_at = _now() - timedelta(days=2)
            row.revoke_reason = 'keyCompromise'
            row.valid_to = _now() - timedelta(days=1)
            db.session.commit()
            if RevokedSerial.query.filter_by(certificate_id=row.id).first() is None:
                _persist(ca_row, serial, valid_to=row.valid_to, certificate_id=row.id)
            _setting('crl_auto_delete_expired_revoked', 'true')

            CRLService.generate_crl(ca['id'])

            db.session.expire_all()
            assert db.session.get(Certificate, cert['id']) is None
            assert not os.path.exists(path)
            records = RevokedSerial.query.filter_by(
                caref=ca_row.refid, serial_number=serial).all()
            assert len(records) == 1
            assert records[0].certificate_id is None
