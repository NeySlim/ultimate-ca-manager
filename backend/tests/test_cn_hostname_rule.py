"""Which CN is a hostname, decided once and honestly (DUP-PKI-012).

Five rules judged a Common Name, and one of them was documented as something
it was not: ``utils.san_parse.cn_looks_like_hostname`` promised
"FQDN / wildcard hostname" and its body was ``'.' in value``. It is the rule
that decides whether the CN is copied into a DNS SAN, so a display-name CN
became a dNSName:

* ``CN=Example, Inc.`` was issued carrying ``DNS:Example, Inc.`` — a 201 and a
  certificate no relying party can match on that name;
* ``CN=café.example.com`` answered 500, because ``x509.DNSName`` refuses a
  U-label and nothing converted it.

The syntactic rule wins, because this decision *grants* an identity. The
neighbouring rule in ``services/trust_store/constraints_mixin`` was left
alone on purpose: it decides whether a CN carries a DNS identity to *check*
against a name constraint, and it must stay the more inclusive of the two.
"""
import pytest

from utils.san_parse import auto_san_buckets_from_cn, cn_looks_like_hostname


@pytest.mark.parametrize('cn,is_hostname', [
    # Display names: a dot does not make a hostname.
    ('Example, Inc.', False),
    ('Acme S.A.', False),
    ('John Doe v2.0', False),
    ('John Doe', False),
    # Not ASCII: x509.DNSName refuses it, so it is not a name UCM can emit.
    ('café.example.com', False),
    # The wildcard short-circuit used to accept this outright.
    ('*. ', False),
    ('*.', False),
    # Real hostnames; no underscore in a dNSName (RFC 5280 §4.2.1.6).
    ('web.example.com', True),
    ('*.example.com', True),
    ('host_name.example.com', False),
    ('_sip._tcp.example.com', False),
    ('srv-1.corp.example', True),
    ('3.5', True),
    ('example.com.', True),
    # Still not hostnames.
    ('localhost', False),
    ('user@example.com', False),
    ('10.0.0.1', False),
    ('-bad.example.com', False),
    ('a' * 64 + '.example.com', False),
    ('', False),
])
def test_cn_looks_like_hostname_matches_its_docstring(cn, is_hostname):
    assert cn_looks_like_hostname(cn) is is_hostname


@pytest.mark.parametrize('cn,expected_dns', [
    ('Example, Inc.', []),
    ('café.example.com', []),
    ('web.example.com', ['web.example.com']),
])
def test_only_a_hostname_cn_becomes_a_dns_san(cn, expected_dns):
    assert auto_san_buckets_from_cn(cn, 'server')['san_dns'] == expected_dns


def test_a_display_name_cn_is_issued_without_a_bogus_dns_san(auth_client, create_ca):
    ca = create_ca(cn='CN rule CA')
    response = auth_client.post('/api/v2/certificates', json={
        'cn': 'Example, Inc.', 'ca_id': ca['id'],
        'cert_type': 'server', 'validity_days': 30,
    })
    assert response.status_code == 201
    assert response.get_json()['data']['san_dns'] in ([], '[]', None)


def test_a_non_ascii_cn_no_longer_answers_500(auth_client, create_ca):
    """It reached x509.DNSName and raised there."""
    ca = create_ca(cn='CN rule CA idn')
    response = auth_client.post('/api/v2/certificates', json={
        'cn': 'café.example.com', 'ca_id': ca['id'],
        'cert_type': 'server', 'validity_days': 30,
    })
    assert response.status_code == 201


def test_the_name_constraints_rule_stays_the_inclusive_one():
    """It answers a different question and must not delegate here."""
    from services.trust_store.constraints_mixin import _DNS_LIKE_CN

    # An IP-shaped CN is a DNS identity for the constraint check, and is not a
    # hostname for the SAN-granting rule.
    assert bool(_DNS_LIKE_CN.match('10.0.0.1')) is True
    assert cn_looks_like_hostname('10.0.0.1') is False
