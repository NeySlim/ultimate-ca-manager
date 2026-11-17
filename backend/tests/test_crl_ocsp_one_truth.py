"""A relying party gets one answer, whichever channel it trusts.

The CRL builder and the OCSP responder read the same three columns —
``revoked``, ``valid_to``, ``revoke_reason`` — and each had its own rules for
them. Three of those rules only existed on one side, so the same certificate
was revoked over OCSP and absent from the CRL, or carried two different
revocation reasons:

* a revoked row with no ``valid_to`` was dropped by ``valid_to > now``, which
  answers NULL and never true;
* a revoked sub-CA whose ``serial_number`` column is empty (imports, and rows
  from before 2.226) was dropped before its certificate was ever read, while
  the responder resolves such a record against that certificate;
* ``cACompromise``, the spelling ``normalize_revocation_reason`` stores, was
  in the CRL's reason table and not in the responder's copy of it.

Two divergences are deliberate and pinned here rather than removed: an
expired certificate needs no CRL entry (RFC 5280 §5), and a serial wider than
20 octets cannot go in one (RFC 5280 §4.1.2.2).
"""
import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import NameOID

from models import db, CA, Certificate
from services.crl_service import CRLService
from services.ocsp_service import OCSPService

from tests.test_serial_encoding_crl_ocsp import _make_ca, _issue, _store, _key


def _crl_serials(ca_id):
    meta = CRLService.generate_crl(ca_id)
    return [entry.serial_number for entry in
            x509.load_pem_x509_crl(meta.crl_pem.encode())]


def _revoked_child_ca(parent, parent_key, parent_cert, refid, serial, *,
                      serial_column, valid_to_days=180):
    """A revoked sub-CA under ``parent``, its serial column spelled as given."""
    now = datetime.now(timezone.utc)
    child_key = _key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, refid)])
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(parent_cert.subject)
            .public_key(child_key.public_key()).serial_number(serial)
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=valid_to_days))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(parent_key, hashes.SHA256()))
    child = CA(
        refid=refid, descr=refid, serial=0, caref=parent.refid,
        serial_number=serial_column,
        crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
        subject=name.rfc4514_string(), issuer=parent_cert.subject.rfc4514_string(),
        revoked=True, revoked_at=now.replace(tzinfo=None),
        revoke_reason='keyCompromise',
        valid_to=(now + timedelta(days=valid_to_days)).replace(tzinfo=None))
    db.session.add(child)
    db.session.commit()
    return child


class TestARevocationWithNoRecordedExpiry:

    def test_it_reaches_the_crl_the_responder_already_answers_for(self, app):
        """``valid_to > now`` answers NULL for a row that never recorded one
        — neither true nor false — and the revocation was dropped in
        silence. SQLite and PostgreSQL agree on that, so it was dropped on
        both."""
        with app.app_context():
            ca, ca_key, ca_cert = _make_ca('novalid-ca', 'No Validity CA')
            leaf = _issue(ca_key, ca_cert, 'novalid.example.com', 0xD0D0)
            row = _store(ca, leaf, 'novalid-leaf', str(0xD0D0))
            row.valid_to = None
            db.session.commit()

            _, ocsp_status, _, _ = OCSPService._status_for_serial(ca, 0xD0D0)

            assert ocsp_status == 'revoked'
            assert 0xD0D0 in _crl_serials(ca.id), (
                'OCSP answers revoked and the CRL does not list it')

    def test_a_sub_ca_with_no_recorded_expiry_reaches_it_too(self, app):
        with app.app_context():
            parent, parent_key, parent_cert = _make_ca('novalid-parent', 'No Validity Parent')
            child = _revoked_child_ca(parent, parent_key, parent_cert,
                                      'novalid-child', 0xD1D1,
                                      serial_column=str(0xD1D1))
            child.valid_to = None
            db.session.commit()

            assert 0xD1D1 in _crl_serials(parent.id)

    def test_an_expired_revocation_is_still_left_off(self, app):
        """Deliberate, and pinned: RFC 5280 §5 — a client rejects an expired
        certificate on its own dates, so the CRL need not carry it. The
        responder still answers revoked for it; that is the documented
        difference, not a defect."""
        with app.app_context():
            ca, ca_key, ca_cert = _make_ca('expired-ca', 'Expired CA')
            leaf = _issue(ca_key, ca_cert, 'expired.example.com', 0xDEAD)
            row = _store(ca, leaf, 'expired-leaf', str(0xDEAD))
            row.valid_to = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
            db.session.commit()

            assert 0xDEAD not in _crl_serials(ca.id)


class TestASubCaWithoutItsSerialColumn:

    def test_its_revocation_reaches_the_crl(self, app):
        """The column is filled at creation since 2.226; an older row and an
        import have none. The certificate has always carried the serial."""
        with app.app_context():
            parent, parent_key, parent_cert = _make_ca('noserial-parent', 'No Serial Parent')
            _revoked_child_ca(parent, parent_key, parent_cert,
                              'noserial-child', 0xE0E0, serial_column='')

            _, ocsp_status, _, _ = OCSPService._status_for_serial(parent, 0xE0E0)

            assert ocsp_status == 'revoked'
            assert 0xE0E0 in _crl_serials(parent.id), (
                'the sub-CA is revoked over OCSP and absent from the CRL')

    def test_a_record_with_neither_is_still_skipped(self, app):
        """Nothing to read, nothing to publish — and no entry invented."""
        with app.app_context():
            from services.crl.generation import _parse_revoked_serial

            orphan = Certificate(refid='nothing-leaf', descr='nothing',
                                 serial_number=None, crt=None)

            assert _parse_revoked_serial(orphan, context='CRL') is None


class TestOneReasonTable:

    @pytest.mark.parametrize('reason,expected', [
        ('cACompromise', x509.ReasonFlags.ca_compromise),
        ('keyCompromise', x509.ReasonFlags.key_compromise),
        ('superseded', x509.ReasonFlags.superseded),
        ('aACompromise', x509.ReasonFlags.aa_compromise),
        ('privilegeWithdrawn', x509.ReasonFlags.privilege_withdrawn),
        ('cessationOfOperation', x509.ReasonFlags.cessation_of_operation),
        ('affiliationChanged', x509.ReasonFlags.affiliation_changed),
    ])
    def test_the_crl_and_the_responder_name_the_same_reason(self, app, reason, expected):
        """Every spelling the revoke API stores, read the same way by both."""
        with app.app_context():
            serial = 0x6000 + abs(hash(reason)) % 0x0FFF
            ca, ca_key, ca_cert = _make_ca(f'reason-{reason}-ca', f'Reason {reason} CA')
            leaf = _issue(ca_key, ca_cert, f'{reason.lower()}.example.com', serial)
            row = _store(ca, leaf, f'reason-{reason}-leaf', str(serial))
            row.revoke_reason = reason
            db.session.commit()

            entry = [e for e in x509.load_pem_x509_crl(
                CRLService.generate_crl(ca.id).crl_pem.encode())
                if e.serial_number == serial][0]
            crl_reason = entry.extensions.get_extension_for_class(
                x509.CRLReason).value.reason
            _, _, _, ocsp_reason = OCSPService._status_for_serial(ca, serial)

            assert crl_reason == expected
            assert ocsp_reason == expected

    def test_the_responder_keeps_its_own_rule_on_remove_from_crl(self):
        """Deliberate, and pinned: ``removeFromCRL`` is a delta-CRL
        instruction (RFC 5280 §5.3.1). The unhold path stages it on the row
        for as long as it takes to publish that delta, and a responder,
        having no delta, must not repeat it."""
        from services.crl._constants import REASON_MAP
        from services.ocsp_service import _REASON_MAP

        assert REASON_MAP['removeFromCRL'] is x509.ReasonFlags.remove_from_crl
        assert 'removeFromCRL' not in _REASON_MAP

    def test_the_two_tables_agree_everywhere_else(self):
        """They were two copies and drifted. One table now, so they cannot."""
        from services.crl._constants import REASON_MAP
        from services.ocsp_service import _REASON_MAP
        from utils.revocation_reasons import REVOCATION_REASONS

        for name in REVOCATION_REASONS:
            assert REASON_MAP[name] is _REASON_MAP[name], name


class TestASerialTooWideForACrl:

    def test_it_stays_off_the_crl_and_the_responder_still_answers(self, app):
        """Deliberate, and pinned: RFC 5280 §4.1.2.2 caps a serial at 20
        octets, and ``cryptography`` refuses to build the entry at all.
        Publishing it would cost the whole CRL, so the revocation is left to
        the responder, which has no such limit. The error log is the signal
        an operator gets."""
        with app.app_context():
            ca, ca_key, ca_cert = _make_ca('wide-ca', 'Wide Serial CA')
            now = datetime.now(timezone.utc)
            oversized = (1 << 160) | 0xDEADBEEF
            row = Certificate(
                refid='wide-leaf', descr='wide', caref=ca.refid, crt=None,
                serial_number=str(oversized),
                revoked=True, revoked_at=now.replace(tzinfo=None),
                revoke_reason='keyCompromise',
                valid_to=(now + timedelta(days=90)).replace(tzinfo=None))
            db.session.add(row)
            db.session.commit()

            assert oversized not in _crl_serials(ca.id)
