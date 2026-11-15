"""The two DN comparators, side by side, on the names they judge differently.

``utils.dn_match.same_name`` is the RFC 5280 §7.1 rule: "the same number of RDNs, for each RDN in
DN1 there is a matching RDN in DN2, and the matching RDNs appear in the same order", values
prepared by RFC 4518 (case folding, NFKC, insignificant spaces). It decides the unique subject,
the EST and WSTEP renewal identity and ``subject_key``.

``services.mtls_enrollment.dn_attributes`` reads an issuer DN a proxy forwards as text, whose
RDN order depends on the proxy (RFC 4514 reversed, OpenSSL's legacy form): it compares sets of
(type, value), order ignored. It only ranks the enrolments sharing a serial; the presented
certificate's fingerprint or DER settles the login (``mtls_auth_service``).
"""
from cryptography import x509
from cryptography.x509.oid import NameOID

from services.mtls_enrollment import dn_attributes
from utils.dn_match import same_name

CN, O, OU = NameOID.COMMON_NAME, NameOID.ORGANIZATION_NAME, NameOID.ORGANIZATIONAL_UNIT_NAME


def _name(*rdns):
    return x509.Name([x509.RelativeDistinguishedName([x509.NameAttribute(oid, value) for oid, value in rdn])
                      for rdn in rdns])


def test_reordered_rdns_are_one_issuer_for_mtls_and_two_names_for_rfc_5280():
    """pins how both comparators judge reordered RDNs; proves no fix."""
    a, b = _name([(CN, 'Issuing CA')], [(O, 'Example')]), _name([(O, 'Example')], [(CN, 'Issuing CA')])
    assert dn_attributes(a) == dn_attributes(b)
    assert not same_name(a, b)


def test_a_multi_valued_rdn_and_two_rdns_are_one_issuer_for_mtls_only():
    """pins how both comparators judge a multi-valued RDN against two RDNs; proves no fix."""
    a, b = _name([(CN, 'Issuing CA'), (O, 'Example')]), _name([(CN, 'Issuing CA')], [(O, 'Example')])
    assert dn_attributes(a) == dn_attributes(b)
    assert not same_name(a, b)


def test_a_repeated_attribute_is_counted_once_by_mtls_only():
    """pins how both comparators judge a repeated attribute; proves no fix."""
    a, b = _name([(OU, 'PKI')], [(OU, 'PKI')], [(CN, 'Issuing CA')]), _name([(OU, 'PKI')], [(CN, 'Issuing CA')])
    assert dn_attributes(a) == dn_attributes(b)
    assert not same_name(a, b)


def test_rfc_4518_mapping_and_nfkc_make_one_name_that_mtls_reads_as_two():
    """pins how both comparators judge names RFC 4518 maps or normalises; proves no fix."""
    # U+FF26 FULLWIDTH F is "F" after NFKC (§2.3); U+00AD SOFT HYPHEN maps to nothing (§2.2)
    for left, right in (('\uff26ile server', 'File Server'), ('Issu\u00ading CA', 'issuing ca')):
        a, b = _name([(CN, left)]), _name([(CN, right)])
        assert same_name(a, b)
        assert dn_attributes(a) != dn_attributes(b)


def test_a_prohibited_code_point_is_compared_where_rfc_4518_says_undefined():
    """pins that a prohibited code point is compared after case folding; proves no fix."""
    # RFC 4518 §2.4: a private use code point fails the preparation, the assertion is Undefined.
    # Not applied: the two names are equal after case folding, the stricter reading for a
    # unique subject (taken), and no key or account is gained by it on a renewal.
    a, b = _name([(CN, 'host\ue000')]), _name([(CN, 'HOST\ue000')])
    assert same_name(a, b)
