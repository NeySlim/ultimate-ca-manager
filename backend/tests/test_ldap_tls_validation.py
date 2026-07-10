"""Regression test: LDAP TLS must validate the server certificate when 'verify SSL' is
enabled, even if no explicit CA bundle is configured. Previously `_build_ldap_tls`
returned None in that case, leaving ldap3 on its default (unvalidated) TLS — a "verify
SSL" setting that silently didn't verify (MITM risk on LDAP auth)."""
import ssl
from types import SimpleNamespace

from api.v2.sso.helpers import _build_ldap_tls


def _provider(**kw):
    d = dict(ldap_verify_ssl=None, ldap_use_ssl=True, ldap_ca_bundle=None)
    d.update(kw)
    return SimpleNamespace(**d)


def test_verify_on_without_ca_bundle_still_validates():
    tls = _build_ldap_tls(_provider(ldap_verify_ssl=True, ldap_ca_bundle=None))
    assert tls is not None, "verify=on must not yield an unvalidated (None) TLS"
    assert tls.validate == ssl.CERT_REQUIRED


def test_default_verify_is_on_and_validates():
    # ldap_verify_ssl unset (None) -> defaults to True -> must validate
    tls = _build_ldap_tls(_provider(ldap_verify_ssl=None, ldap_ca_bundle=None))
    assert tls is not None and tls.validate == ssl.CERT_REQUIRED


def test_verify_off_is_cert_none():
    tls = _build_ldap_tls(_provider(ldap_verify_ssl=False))
    assert tls is not None and tls.validate == ssl.CERT_NONE


def test_verify_on_with_ca_bundle_validates():
    pem = "-----BEGIN CERTIFICATE-----\nMIIBmock\n-----END CERTIFICATE-----\n"
    tls = _build_ldap_tls(_provider(ldap_verify_ssl=True, ldap_ca_bundle=pem))
    assert tls.validate == ssl.CERT_REQUIRED
