"""Regression tests: ACME CSR *subject* injection (follow-up to PR #242).

PR #242 made ACME finalize reject SAN general-name types the order never
validated, but the CSR *subject* still leaked two identities into the issued
certificate, past that SAN check:

  1. No-SAN CSR + subject emailAddress. ``_validate_csr_san_types`` returns
     (True, None) when the CSR has no SubjectAlternativeName, but sign_csr then
     SYNTHESIZES a SAN from the subject — a DNSName from the CN and an
     rfc822Name for every ``emailAddress`` RDN. An order authorizing only
     dns:web.example.com, finalized with a CSR whose subject is
     ``CN=web.example.com, emailAddress=ceo@victim.com`` and NO SAN extension,
     yielded a leaf carrying ``RFC822Name('ceo@victim.com')`` — an identity the
     account never proved, which email-based client-certificate identity
     mapping (mTLS, EAP-TLS, VPN) keys on.

  2. Multiple CNs. Finalize compared only the FIRST CN to the order, and
     sign_csr copies the subject verbatim onto the leaf. A CSR with subject
     ``CN=web.example.com, CN=admin.victim.com`` and SAN=[dns:web.example.com]
     for an order authorizing only web.example.com passed every check, and the
     leaf carried the unvalidated ``admin.victim.com`` — which, because the
     stored ``subject_cn`` is the first CN of the RFC 4514 (reversed) DN, even
     became the certificate's displayed identity.

The fix adds ``_validate_csr_subject``: every CN must be a validated order
identifier and no emailAddress RDN may appear. These are the only two subject
attribute types sign_csr turns into SAN general names.

The unit tests exercise the validator directly (no DB/order needed). The
``TestFinalizeOrderRejectsSubjectInjection`` class drives the real
finalize_order path (Flask app fixture; runs in CI) and asserts the smuggled
subject never reaches the signer.
"""
import ipaddress

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from services.acme.acme_service import AcmeService


@pytest.fixture(scope='module')
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _csr(signing_key, subject_attrs, san_entries=None):
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name(subject_attrs)
    )
    if san_entries:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(san_entries), critical=False
        )
    return builder.sign(signing_key, hashes.SHA256())


def _cn(value):
    return x509.NameAttribute(NameOID.COMMON_NAME, value)


def _email(value):
    return x509.NameAttribute(NameOID.EMAIL_ADDRESS, value)


def _validate(csr, domains=frozenset({'web.example.com'}), ips=frozenset()):
    """Call the subject validator the way finalize_order does."""
    return AcmeService._validate_csr_subject(csr, set(domains), set(ips))


# --- the authorized cases still work ---------------------------------------

def test_single_cn_matching_order_is_accepted(signing_key):
    csr = _csr(signing_key, [_cn('web.example.com')],
               [x509.DNSName('web.example.com')])
    ok, err = _validate(csr)
    assert ok, err


def test_single_cn_without_san_is_accepted(signing_key):
    """The legitimate no-SAN flow #242's test_csr_without_san_extension_is_accepted
    covers must still pass: a CN that matches the order and no email."""
    csr = _csr(signing_key, [_cn('web.example.com')], None)
    ok, err = _validate(csr)
    assert ok, err


def test_cn_is_case_and_trailing_dot_insensitive(signing_key):
    csr = _csr(signing_key, [_cn('WEB.Example.COM.')], None)
    ok, err = _validate(csr)
    assert ok, err


def test_ip_cn_matching_ip_order_is_accepted(signing_key):
    csr = _csr(signing_key, [_cn('203.0.113.10')], None)
    ok, err = _validate(csr, domains=frozenset(), ips=frozenset({'203.0.113.10'}))
    assert ok, err


def test_empty_subject_san_only_is_accepted(signing_key):
    """A SAN-only CSR with no subject RDNs has nothing to validate here."""
    csr = _csr(signing_key, [], [x509.DNSName('web.example.com')])
    ok, err = _validate(csr)
    assert ok, err


# --- Finding 1: emailAddress in the subject --------------------------------

def test_email_subject_without_san_is_rejected(signing_key):
    """The core exploit: no SAN extension, so sign_csr would synthesize an
    rfc822Name from the emailAddress RDN."""
    csr = _csr(signing_key, [
        _cn('web.example.com'),           # matches the order
        _email('ceo@victim.com'),         # never proved
    ], None)
    ok, err = _validate(csr)
    assert not ok
    assert 'emailAddress' in err
    assert 'ceo@victim.com' in err


def test_email_subject_is_rejected_even_with_matching_san(signing_key):
    """The subject is copied onto the leaf regardless of the SAN extension."""
    csr = _csr(signing_key, [
        _cn('web.example.com'),
        _email('ceo@victim.com'),
    ], [x509.DNSName('web.example.com')])
    ok, err = _validate(csr)
    assert not ok
    assert 'emailAddress' in err


def test_email_shaped_cn_is_rejected(signing_key):
    """An '@'-bearing CN is synthesized into an rfc822Name too, and matches no
    DNS/IP identifier."""
    csr = _csr(signing_key, [_cn('ceo@victim.com')], None)
    ok, err = _validate(csr)
    assert not ok


# --- Finding 2: unvalidated additional CN ----------------------------------

def test_second_cn_outside_order_is_rejected(signing_key):
    csr = _csr(signing_key, [
        _cn('web.example.com'),           # matches the order
        _cn('admin.victim.com'),          # never proved — index > 0
    ], [x509.DNSName('web.example.com')])
    ok, err = _validate(csr)
    assert not ok
    assert 'admin.victim.com' in err


def test_second_cn_rejected_even_without_san(signing_key):
    csr = _csr(signing_key, [
        _cn('web.example.com'),
        _cn('admin.victim.com'),
    ], None)
    ok, err = _validate(csr)
    assert not ok
    assert 'admin.victim.com' in err


def test_sole_unauthorized_cn_is_rejected(signing_key):
    csr = _csr(signing_key, [_cn('admin.victim.com')], None)
    ok, err = _validate(csr)
    assert not ok
    assert 'admin.victim.com' in err


# --- end-to-end: the smuggled subject must stop finalize before signing ----

class TestFinalizeOrderRejectsSubjectInjection:
    """Drive the real finalize_order path.

    ``_sign_certificate_with_ca`` is stubbed to record whether issuance was
    reached at all. Before the fix, a CSR carrying an unproven email/second-CN
    subject sailed through validation and the stub was invoked (a real
    deployment would have signed the certificate); after the fix, finalize
    fails during identifier validation and signing is never reached.
    """

    def _order(self, app, identifiers):
        import json as _json
        import uuid as _uuid
        from models import db
        from models.acme_models import AcmeAccount, AcmeOrder

        acct = AcmeAccount(
            jwk='{}',
            jwk_thumbprint=_uuid.uuid4().hex + _uuid.uuid4().hex[:11],
            status='valid',
        )
        db.session.add(acct)
        db.session.flush()
        order = AcmeOrder(
            account_id=acct.account_id,
            status='ready',
            identifiers=_json.dumps(identifiers),
        )
        db.session.add(order)
        db.session.commit()
        return order

    def _run_finalize(self, app, monkeypatch, subject_attrs, san_entries):
        from cryptography.hazmat.primitives import serialization

        with app.app_context():
            order = self._order(
                app, [{'type': 'dns', 'value': 'web.example.com'}]
            )
            service = AcmeService(base_url='http://localhost')

            from utils import caa_checker
            monkeypatch.setattr(
                caa_checker, 'check_caa_for_domains',
                lambda *a, **k: (True, 'allowed'),
            )
            monkeypatch.setattr(
                service, '_resolve_ca_for_domains', lambda _d: 'test-ca'
            )
            reached = {'signing': False}

            def _stub_sign(**_kwargs):
                reached['signing'] = True
                return False, None, 'signing failed'

            monkeypatch.setattr(service, '_sign_certificate_with_ca', _stub_sign)

            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            csr = _csr(key, subject_attrs, san_entries)
            csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode()

            service.begin_order_processing(order)
            service._finalizing_order_id = order.order_id
            success, error = service.finalize_order(order.order_id, csr_pem)
            service._finalizing_order_id = None
            return success, error, reached['signing']

    def test_clean_csr_reaches_signing(self, app, monkeypatch):
        """Control: an honest CSR still gets through to issuance."""
        success, error, reached_signing = self._run_finalize(
            app, monkeypatch,
            [_cn('web.example.com')],
            [x509.DNSName('web.example.com')],
        )
        assert reached_signing, 'validation wrongly blocked a legitimate CSR'
        assert error == 'signing failed'

    def test_no_san_email_subject_never_reaches_signing(self, app, monkeypatch):
        success, error, reached_signing = self._run_finalize(
            app, monkeypatch,
            [_cn('web.example.com'), _email('ceo@victim.com')],
            None,
        )
        assert not success
        assert not reached_signing, (
            'CSR with an unproven emailAddress subject reached the signer — a '
            'real deployment would have issued a cert asserting ceo@victim.com'
        )
        assert 'emailAddress' in error

    def test_multi_cn_never_reaches_signing(self, app, monkeypatch):
        success, error, reached_signing = self._run_finalize(
            app, monkeypatch,
            [_cn('web.example.com'), _cn('admin.victim.com')],
            [x509.DNSName('web.example.com')],
        )
        assert not success
        assert not reached_signing, (
            'CSR with an unproven second CN reached the signer — a real '
            'deployment would have issued (and displayed) admin.victim.com'
        )
        assert 'admin.victim.com' in error
