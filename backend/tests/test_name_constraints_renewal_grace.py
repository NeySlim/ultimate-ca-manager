"""Regression tests for the 2.200 NameConstraints enforcement sweep.

1. Renewal at par: a certificate issued before constraint enforcement (or
   before the CA's constraints tightened) must stay renewable — its existing
   names are graced; only names NEW to the request are enforced.
2. A non-hostname CN ("John Doe") carries no DNS identity and must not be
   validated against DNS permitted subtrees.
3. A NameConstraints extension cryptography cannot parse must not block
   issuance (warning + skip), matching pre-2.200 behaviour on these paths.
"""
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from services.trust_store.constraints_mixin import validate_name_constraints


def _make_ca(permitted_dns=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'NC Test CA')])
    builder = (x509.CertificateBuilder()
               .subject_name(name).issuer_name(name)
               .public_key(key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
               .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
               .add_extension(x509.BasicConstraints(ca=True, path_length=None),
                              critical=True))
    if permitted_dns:
        builder = builder.add_extension(
            x509.NameConstraints(
                permitted_subtrees=[x509.DNSName(d) for d in permitted_dns],
                excluded_subtrees=None,
            ),
            critical=True,
        )
    return builder.sign(key, hashes.SHA256()), key


def _make_leaf(ca_cert, ca_key, cn, sans=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = (x509.CertificateBuilder()
               .subject_name(x509.Name(
                   [x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
               .issuer_name(ca_cert.subject)
               .public_key(key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
               .not_valid_after(datetime.now(timezone.utc) + timedelta(days=90)))
    if sans:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(sans), critical=False)
    return builder.sign(ca_key, hashes.SHA256())


def _subject(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


class TestRenewalGrace:

    def test_out_of_scope_renewal_is_graced(self, app):
        ca_cert, ca_key = _make_ca(permitted_dns=['allowed.test'])
        old = _make_leaf(ca_cert, ca_key, 'legacy.other',
                         sans=[x509.DNSName('legacy.other')])
        with app.app_context():
            # Without grace this raises; with renewal_of it must pass
            validate_name_constraints(
                ca_cert, old.subject, [x509.DNSName('legacy.other')],
                renewal_of=old,
            )

    def test_out_of_scope_without_renewal_still_rejected(self, app):
        ca_cert, ca_key = _make_ca(permitted_dns=['allowed.test'])
        with app.app_context():
            with pytest.raises(ValueError):
                validate_name_constraints(
                    ca_cert, _subject('evil.other'),
                    [x509.DNSName('evil.other')],
                )

    def test_new_names_on_renewal_are_enforced(self, app):
        ca_cert, ca_key = _make_ca(permitted_dns=['allowed.test'])
        old = _make_leaf(ca_cert, ca_key, 'legacy.other',
                         sans=[x509.DNSName('legacy.other')])
        with app.app_context():
            with pytest.raises(ValueError):
                validate_name_constraints(
                    ca_cert, old.subject,
                    [x509.DNSName('legacy.other'), x509.DNSName('added.other')],
                    renewal_of=old,
                )

    def test_in_scope_renewal_passes(self, app):
        ca_cert, ca_key = _make_ca(permitted_dns=['allowed.test'])
        old = _make_leaf(ca_cert, ca_key, 'www.allowed.test',
                         sans=[x509.DNSName('www.allowed.test')])
        with app.app_context():
            validate_name_constraints(
                ca_cert, old.subject, [x509.DNSName('www.allowed.test')],
                renewal_of=old,
            )


class TestCnHeuristic:

    def test_human_cn_not_treated_as_dns(self, app):
        ca_cert, _ = _make_ca(permitted_dns=['allowed.test'])
        with app.app_context():
            # "John Doe" is not a hostname: no DNS identity to constrain
            validate_name_constraints(ca_cert, _subject('John Doe'), None)

    def test_hostname_cn_still_enforced(self, app):
        ca_cert, _ = _make_ca(permitted_dns=['allowed.test'])
        with app.app_context():
            with pytest.raises(ValueError):
                validate_name_constraints(ca_cert, _subject('www.other.test'), None)

    def test_email_cn_checked_as_email(self, app):
        ca_cert, _ = _make_ca(permitted_dns=['allowed.test'])
        with app.app_context():
            # RFC822 name under DNS-only permitted subtrees: no same-type
            # constraint applies → allowed
            validate_name_constraints(ca_cert, _subject('user@corp.test'), None)


class TestMalformedNameConstraints:

    def test_unreadable_nc_is_skipped(self, app, monkeypatch):
        ca_cert, _ = _make_ca(permitted_dns=['allowed.test'])

        class _BoomExtensions:
            def get_extension_for_oid(self, oid):
                raise ValueError('malformed NC payload')

        monkeypatch.setattr(type(ca_cert), 'extensions',
                            property(lambda self: _BoomExtensions()))
        with app.app_context():
            # Pre-2.200 these paths never reached the constraint: an
            # unparseable extension must not brick issuance
            validate_name_constraints(
                ca_cert, _subject('anything.other'),
                [x509.DNSName('anything.other')],
            )
