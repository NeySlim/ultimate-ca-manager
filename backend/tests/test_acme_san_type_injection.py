"""Regression tests: ACME SAN-type injection (security audit v2.203, item #1).

ACME finalize validated the CSR by extracting only dNSName and iPAddress SANs
and comparing those to the order identifiers. Every other general-name type was
neither inspected nor rejected, and sign_csr copies the CSR's SAN extension
verbatim onto the leaf. A client that legitimately passed http-01 for a domain
it controlled could therefore attach:

    SAN: email:ceo@victim.com
    SAN: otherName/UPN: Administrator@corp.local

to the finalize CSR and receive a CA-signed certificate asserting an email
address and a Windows UPN it never proved control of — enabling S/MIME
impersonation and, against a CA trusted for smartcard logon, AD authentication
as another user.

These tests exercise the validator directly (no DB/order needed): the fix is
that _validate_csr_san_types rejects any SAN general name outside the set of
identifiers the order actually validated.
"""
import ipaddress

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from services.acme.acme_service import AcmeService
from utils.upn_san import build_upn_other_name


@pytest.fixture(scope='module')
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _csr_with_san(signing_key, san_entries, cn='web.example.com'):
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    )
    if san_entries:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(san_entries), critical=False
        )
    return builder.sign(signing_key, hashes.SHA256())


def _validate(csr, domains=frozenset({'web.example.com'}), ips=frozenset()):
    """Call the SAN-type validator the way finalize_order does."""
    return AcmeService._validate_csr_san_types(csr, set(domains), set(ips))


# --- the authorized case still works ---------------------------------------

def test_dns_san_matching_order_is_accepted(signing_key):
    csr = _csr_with_san(signing_key, [x509.DNSName('web.example.com')])
    ok, err = _validate(csr)
    assert ok, err


def test_dns_san_is_case_and_trailing_dot_insensitive(signing_key):
    csr = _csr_with_san(signing_key, [x509.DNSName('WEB.Example.COM.')])
    ok, err = _validate(csr)
    assert ok, err


def test_ip_san_matching_order_is_accepted(signing_key):
    csr = _csr_with_san(
        signing_key, [x509.IPAddress(ipaddress.ip_address('203.0.113.10'))]
    )
    ok, err = _validate(csr, domains=frozenset(), ips=frozenset({'203.0.113.10'}))
    assert ok, err


def test_csr_without_san_extension_is_accepted(signing_key):
    csr = _csr_with_san(signing_key, None)
    ok, err = _validate(csr)
    assert ok, err


# --- the vulnerability ------------------------------------------------------

def test_email_san_alongside_authorized_dns_is_rejected(signing_key):
    """The core exploit: a valid DNS SAN carrying a smuggled rfc822Name."""
    csr = _csr_with_san(signing_key, [
        x509.DNSName('web.example.com'),          # matches the order
        x509.RFC822Name('ceo@victim.com'),        # never proved
    ])
    ok, err = _validate(csr)
    assert not ok
    assert 'RFC822Name' in err


def test_upn_othername_san_is_rejected(signing_key):
    """UPN otherName — the AD-logon impersonation vector."""
    csr = _csr_with_san(signing_key, [
        x509.DNSName('web.example.com'),
        build_upn_other_name('Administrator@corp.local'),
    ])
    ok, err = _validate(csr)
    assert not ok
    assert 'OtherName' in err
    # The offending type-id is named so operators can see what was attempted.
    assert '1.3.6.1.4.1.311.20.2.3' in err


def test_uri_san_is_rejected(signing_key):
    csr = _csr_with_san(signing_key, [
        x509.DNSName('web.example.com'),
        x509.UniformResourceIdentifier('spiffe://cluster/ns/default/sa/admin'),
    ])
    ok, err = _validate(csr)
    assert not ok
    assert 'UniformResourceIdentifier' in err


def test_directory_name_san_is_rejected(signing_key):
    csr = _csr_with_san(signing_key, [
        x509.DNSName('web.example.com'),
        x509.DirectoryName(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Domain Admins')])
        ),
    ])
    ok, err = _validate(csr)
    assert not ok
    assert 'DirectoryName' in err


def test_unauthorized_extra_dns_san_is_rejected(signing_key):
    """A second dNSName outside the order must not ride along either."""
    csr = _csr_with_san(signing_key, [
        x509.DNSName('web.example.com'),
        x509.DNSName('mail.victim.com'),
    ])
    ok, err = _validate(csr)
    assert not ok
    assert 'mail.victim.com' in err


def test_unauthorized_ip_san_is_rejected(signing_key):
    csr = _csr_with_san(signing_key, [
        x509.DNSName('web.example.com'),
        x509.IPAddress(ipaddress.ip_address('10.0.0.1')),
    ])
    ok, err = _validate(csr)
    assert not ok
    assert '10.0.0.1' in err


def test_email_san_rejected_even_as_sole_entry(signing_key):
    """No DNS SAN at all — the type check must not depend on ordering."""
    csr = _csr_with_san(signing_key, [x509.RFC822Name('ceo@victim.com')])
    ok, err = _validate(csr)
    assert not ok


# --- end-to-end: the smuggled SAN must stop finalize before signing ---------

class TestFinalizeOrderRejectsSmuggledSan:
    """Drive the real finalize_order path.

    ``_sign_certificate_with_ca`` is stubbed to record whether issuance was
    reached at all. Before the fix, a CSR carrying an unproven UPN/email SAN
    sailed through validation and the stub was invoked (i.e. a real deployment
    would have signed the certificate); after the fix, finalize fails during
    identifier validation and signing is never reached.
    """

    def _order(self, app, identifiers):
        import json as _json
        import uuid as _uuid
        from models import db
        from models.acme_models import AcmeAccount, AcmeOrder

        # jwk_thumbprint is UNIQUE — keep each test's account distinct.
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

    def _run_finalize(self, app, monkeypatch, san_entries):
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
            csr = _csr_with_san(key, san_entries)
            csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode()

            service.begin_order_processing(order)
            service._finalizing_order_id = order.order_id
            success, error = service.finalize_order(order.order_id, csr_pem)
            service._finalizing_order_id = None
            return success, error, reached['signing']

    def test_clean_csr_reaches_signing(self, app, monkeypatch):
        """Control: an honest CSR still gets through to issuance."""
        success, error, reached_signing = self._run_finalize(
            app, monkeypatch, [x509.DNSName('web.example.com')]
        )
        assert reached_signing, 'validation wrongly blocked a legitimate CSR'
        assert error == 'signing failed'

    def test_smuggled_upn_never_reaches_signing(self, app, monkeypatch):
        success, error, reached_signing = self._run_finalize(
            app, monkeypatch, [
                x509.DNSName('web.example.com'),
                build_upn_other_name('Administrator@corp.local'),
            ],
        )
        assert not success
        assert not reached_signing, (
            'CSR with an unproven UPN SAN reached the signer — a real '
            'deployment would have issued the certificate'
        )
        assert 'unauthorized general name type' in error

    def test_smuggled_email_never_reaches_signing(self, app, monkeypatch):
        success, error, reached_signing = self._run_finalize(
            app, monkeypatch, [
                x509.DNSName('web.example.com'),
                x509.RFC822Name('ceo@victim.com'),
            ],
        )
        assert not success
        assert not reached_signing
        assert 'unauthorized general name type' in error
