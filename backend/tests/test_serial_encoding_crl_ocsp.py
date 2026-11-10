"""One certificate, one serial, whichever way the column spells it.

``Certificate.serial_number`` has three writers — decimal ``str(n)``
(services/cert/mixins/lifecycle.py and the import routes), lowercase hex
``format(n, 'x')`` (api/v2/certificates/cert_create.py, services/cert/
renewal.py) and uppercase hex ``format(n, 'X')`` (api/v2/msca.py). An
all-digit column is therefore ambiguous, and the readers disagreed about it:
the OCSP responder settles it against the stored certificate, the CRL
generator read it as decimal, and the ACME ARI lookup confirmed its candidate
the same decimal way.

A certificate of serial 0x12345 stored by the hex writer as ``"12345"``:
the CRL listed 12345 — some other certificate's serial — and left 74565
unlisted, so a client trusting the CRL saw it as valid while a client
trusting OCSP saw it revoked. ARI answered that it had never been issued.
"""
import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import db, CA, Certificate, RevokedSerial
from services.acme.ari import find_certificate
from services.crl_service import CRLService
from services.ocsp_service import OCSPService

@pytest.fixture(autouse=True)
def _remove_what_the_test_stored(app):
    """Every CA and certificate here has a `serial-` refid; they go with their dependents."""
    yield
    from models import CRLMetadata, OCSPResponse
    with app.app_context():
        db.session.rollback()
        ca_ids = [c.id for c in CA.query.filter(CA.refid.like('serial-%')).all()]
        carefs = [c.refid for c in CA.query.filter(CA.refid.like('serial-%')).all()]
        Certificate.query.filter(Certificate.refid.like('serial-%')).delete(synchronize_session=False)
        RevokedSerial.query.filter(RevokedSerial.caref.in_(carefs)).delete(synchronize_session=False)
        for model in (OCSPResponse, CRLMetadata):
            model.query.filter(model.ca_id.in_(ca_ids)).delete(synchronize_session=False)
        CA.query.filter(CA.id.in_(ca_ids)).delete(synchronize_session=False)
        db.session.commit()


# format(0x12345, 'x') == '12345', which reads back as decimal 12345.
AMBIGUOUS_SERIAL = 0x12345
DECIMAL_MISREADING = 12345


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _make_ca(refid, cn):
    """A CA able to sign a CRL, plus its key and certificate."""
    now = datetime.now(timezone.utc)
    ca_key = _key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
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
    ca = CA(refid=refid, descr=cn, serial=0,
            prv=base64.b64encode(ca_key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption())).decode(),
            crt=base64.b64encode(ca_cert.public_bytes(serialization.Encoding.PEM)).decode(),
            subject=name.rfc4514_string(), issuer=name.rfc4514_string(),
            ocsp_enabled=True, cdp_enabled=True)
    db.session.add(ca)
    db.session.commit()
    return ca, ca_key, ca_cert


def _issue(ca_key, ca_cert, cn, serial):
    now = datetime.now(timezone.utc)
    leaf_key = _key()
    return (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .issuer_name(ca_cert.subject)
            .public_key(leaf_key.public_key())
            .serial_number(serial)
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=90))
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))


def _store(ca, leaf, refid, column, *, revoked=True, aki=None):
    """A certificate row whose serial column is spelled ``column``."""
    now = datetime.now(timezone.utc)
    row = Certificate(
        refid=refid, descr=refid, caref=ca.refid,
        crt=base64.b64encode(leaf.public_bytes(serialization.Encoding.PEM)).decode(),
        serial_number=column,
        subject=leaf.subject.rfc4514_string(), issuer=leaf.issuer.rfc4514_string(),
        aki=aki,
        revoked=revoked,
        revoked_at=now.replace(tzinfo=None) if revoked else None,
        revoke_reason='keyCompromise' if revoked else None,
        valid_from=(now - timedelta(days=1)).replace(tzinfo=None),
        valid_to=(now + timedelta(days=90)).replace(tzinfo=None),
    )
    db.session.add(row)
    db.session.commit()
    return row


def _crl_serials(ca_id):
    meta = CRLService.generate_crl(ca_id)
    return sorted(entry.serial_number for entry in
                  x509.load_pem_x509_crl(meta.crl_pem.encode()))


class TestCrlPublishesTheCertificatesSerial:

    def test_a_hex_written_serial_is_not_republished_as_decimal(self, app):
        """The hex writer's ``"12345"`` is 0x12345, not 12345."""
        with app.app_context():
            ca, ca_key, ca_cert = _make_ca('serial-hex-ca', 'Serial Hex CA')
            leaf = _issue(ca_key, ca_cert, 'hex.example.com', AMBIGUOUS_SERIAL)
            _store(ca, leaf, 'serial-hex-leaf', format(AMBIGUOUS_SERIAL, 'x'))

            serials = _crl_serials(ca.id)

            assert AMBIGUOUS_SERIAL in serials, (
                f'the revoked certificate is missing from the CRL: {serials}')
            assert DECIMAL_MISREADING not in serials, (
                'the CRL published a serial no certificate under this CA carries')

    def test_an_uppercase_hex_serial_is_read_the_same_way(self, app):
        """api/v2/msca.py writes ``format(n, 'X')``."""
        with app.app_context():
            ca, ca_key, ca_cert = _make_ca('serial-upper-ca', 'Serial Upper CA')
            leaf = _issue(ca_key, ca_cert, 'upper.example.com', AMBIGUOUS_SERIAL)
            _store(ca, leaf, 'serial-upper-leaf', format(AMBIGUOUS_SERIAL, 'X'))

            assert AMBIGUOUS_SERIAL in _crl_serials(ca.id)

    def test_a_decimal_serial_still_publishes_unchanged(self, app):
        """The decimal writer keeps working: the column and the certificate
        agree, and nothing about that row changes."""
        with app.app_context():
            ca, ca_key, ca_cert = _make_ca('serial-dec-ca', 'Serial Dec CA')
            leaf = _issue(ca_key, ca_cert, 'dec.example.com', DECIMAL_MISREADING)
            _store(ca, leaf, 'serial-dec-leaf', str(DECIMAL_MISREADING))

            assert _crl_serials(ca.id) == [DECIMAL_MISREADING]

    def test_a_row_without_its_certificate_falls_back_on_the_column(self, app):
        """A RevokedSerial has no certificate to read — the column is all
        there is, and it is still published."""
        with app.app_context():
            ca, _, _ = _make_ca('serial-orphan-ca', 'Serial Orphan CA')
            now = datetime.now(timezone.utc)
            db.session.add(RevokedSerial(
                caref=ca.refid, serial_number='4242',
                revoked_at=now.replace(tzinfo=None), revoke_reason='keyCompromise',
                valid_to=(now + timedelta(days=90)).replace(tzinfo=None)))
            db.session.commit()

            assert 4242 in _crl_serials(ca.id)


class TestCrlAndOcspAgree:

    def test_both_answer_revoked_for_the_same_serial(self, app):
        """The two answers a relying party can get must be one answer."""
        with app.app_context():
            ca, ca_key, ca_cert = _make_ca('serial-agree-ca', 'Serial Agree CA')
            leaf = _issue(ca_key, ca_cert, 'agree.example.com', AMBIGUOUS_SERIAL)
            _store(ca, leaf, 'serial-agree-leaf', format(AMBIGUOUS_SERIAL, 'x'))

            _, ocsp_status, _, _ = OCSPService._status_for_serial(ca, AMBIGUOUS_SERIAL)
            on_crl = AMBIGUOUS_SERIAL in _crl_serials(ca.id)

            assert ocsp_status == 'revoked'
            assert on_crl, 'OCSP says revoked and the CRL does not list it'


class TestOneCertificateIsOneEntry:

    def test_a_hex_row_and_its_decimal_revocation_record_are_not_listed_twice(self, app):
        """The live row spells the serial in hex, the persistent record in
        decimal. They are one certificate and one CRL entry."""
        with app.app_context():
            ca, ca_key, ca_cert = _make_ca('serial-dup-ca', 'Serial Dup CA')
            leaf = _issue(ca_key, ca_cert, 'dup.example.com', AMBIGUOUS_SERIAL)
            _store(ca, leaf, 'serial-dup-leaf', format(AMBIGUOUS_SERIAL, 'x'))
            now = datetime.now(timezone.utc)
            db.session.add(RevokedSerial(
                caref=ca.refid, serial_number=str(AMBIGUOUS_SERIAL),
                revoked_at=now.replace(tzinfo=None), revoke_reason='keyCompromise',
                valid_to=(now + timedelta(days=90)).replace(tzinfo=None)))
            db.session.commit()

            serials = _crl_serials(ca.id)

            assert serials == [AMBIGUOUS_SERIAL], (
                f'expected one entry for one certificate, got {serials}')


class TestDeltaCrl:

    def test_the_delta_publishes_the_certificates_serial_too(self, app):
        """The delta builds its entries through the same helper."""
        with app.app_context():
            ca, ca_key, ca_cert = _make_ca('serial-delta-ca', 'Serial Delta CA')
            ca.delta_crl_enabled = True
            db.session.commit()
            CRLService.generate_crl(ca.id)

            leaf = _issue(ca_key, ca_cert, 'delta.example.com', AMBIGUOUS_SERIAL)
            _store(ca, leaf, 'serial-delta-leaf', format(AMBIGUOUS_SERIAL, 'x'))

            meta = CRLService.generate_delta_crl(ca.id)
            serials = sorted(e.serial_number for e in
                             x509.load_pem_x509_crl(meta.crl_pem.encode()))

            assert AMBIGUOUS_SERIAL in serials
            assert DECIMAL_MISREADING not in serials


class TestAriFindsTheCertificate:

    def test_renewal_information_is_served_for_a_hex_written_serial(self, app):
        """RFC 9773: the ARI lookup must find the certificate the client
        names, whichever writer filled its serial column."""
        with app.app_context():
            ca, ca_key, ca_cert = _make_ca('serial-ari-ca', 'Serial ARI CA')
            aki_hex = x509.SubjectKeyIdentifier.from_public_key(
                ca_key.public_key()).digest.hex()
            leaf = _issue(ca_key, ca_cert, 'ari.example.com', AMBIGUOUS_SERIAL)
            row = _store(ca, leaf, 'serial-ari-leaf', format(AMBIGUOUS_SERIAL, 'x'),
                         revoked=False, aki=aki_hex)

            found = find_certificate(aki_hex, AMBIGUOUS_SERIAL)

            assert found is not None, 'ARI reported a certificate it had issued as unknown'
            assert found.id == row.id


class TestRevocationClearsTheOcspCache:

    def test_a_hex_written_serial_clears_the_good_it_had_cached(self, app):
        """RFC 6960 §2.2 — the responder must stop answering ``good`` at
        once. Entries are keyed by the certificate's real serial in hex;
        callers invalidate with the column, and the two did not meet."""
        from models import OCSPResponse

        with app.app_context():
            ca, ca_key, ca_cert = _make_ca('serial-cache-ca', 'Serial Cache CA')
            leaf = _issue(ca_key, ca_cert, 'cache.example.com', AMBIGUOUS_SERIAL)
            row = _store(ca, leaf, 'serial-cache-leaf', format(AMBIGUOUS_SERIAL, 'x'),
                         revoked=False)

            _, status = OCSPService().generate_response(ca, AMBIGUOUS_SERIAL)
            assert status == 'good'
            assert OCSPResponse.query.filter_by(ca_id=ca.id).count() == 1

            row.revoked = True
            row.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
            row.revoke_reason = 'keyCompromise'
            db.session.commit()
            OCSPService.invalidate_cached_responses(row.serial_number, ca_id=ca.id)

            assert OCSPResponse.query.filter_by(ca_id=ca.id).count() == 0, (
                'a cached "good" survived the revocation of its certificate')

    def test_a_decimal_written_serial_still_clears(self, app):
        """The decimal writer's column already matched — it still does."""
        from models import OCSPResponse

        with app.app_context():
            ca, ca_key, ca_cert = _make_ca('serial-cache-dec-ca', 'Serial Cache Dec CA')
            leaf = _issue(ca_key, ca_cert, 'cachedec.example.com', DECIMAL_MISREADING)
            row = _store(ca, leaf, 'serial-cache-dec-leaf', str(DECIMAL_MISREADING),
                         revoked=False)

            OCSPService().generate_response(ca, DECIMAL_MISREADING)
            assert OCSPResponse.query.filter_by(ca_id=ca.id).count() == 1

            OCSPService.invalidate_cached_responses(row.serial_number, ca_id=ca.id)

            assert OCSPResponse.query.filter_by(ca_id=ca.id).count() == 0
