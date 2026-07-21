"""LDAP DN parsing regression tests for escaped and multivalued RDNs."""

from utils.dn_parse import get_dn_attribute, get_parent_dn


def test_extracts_cn_with_escaped_comma():
    dn = r'CN=Doe\, John,OU=Groups,DC=example,DC=com'
    assert get_dn_attribute(dn, 'CN') == 'Doe, John'


def test_extracts_cn_with_escaped_plus_from_multivalued_rdn():
    dn = r'CN=Ops\+Platform+OU=Privileged,DC=example,DC=com'
    assert get_dn_attribute(dn, 'cn') == 'Ops+Platform'


def test_extracts_quoted_cn():
    dn = 'CN="Doe, John",OU=Groups,DC=example,DC=com'
    assert get_dn_attribute(dn, 'CN') == 'Doe, John'


def test_parent_dn_skips_complete_multivalued_first_rdn():
    dn = r'UID=alice+CN=Doe\, John,OU=People,DC=example,DC=com'
    assert get_parent_dn(dn) == 'OU=People,DC=example,DC=com'


def test_parent_dn_handles_escaped_comma_in_first_rdn():
    dn = r'OU=People\, Contractors,DC=example,DC=com'
    assert get_parent_dn(dn) == 'DC=example,DC=com'
