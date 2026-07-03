"""Unit tests for SSH setup script parameter validation."""

from api.v2.ssh.validation import validate_setup_hostname


def test_validate_setup_hostname_allows_empty():
    assert validate_setup_hostname('') is None


def test_validate_setup_hostname_allows_safe_fqdn():
    assert validate_setup_hostname('web01.example.com') is None
    assert validate_setup_hostname('host-1_sub') is None


def test_validate_setup_hostname_rejects_injection():
    assert validate_setup_hostname('$(id)') is not None
    assert validate_setup_hostname('x";id;"') is not None
    assert validate_setup_hostname('host name') is not None
