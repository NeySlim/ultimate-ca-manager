"""A refused SSO sign-in tells the administrator what was read, from where, bounded.

Unit level: the texts, their bounds, the neutralisation for the log, the claim
lookup of an attribute mapping row to ``groups`` and the bounded "Role resolution"
line. The doors themselves are tested with their protocol: OIDC in
test_sso_oidc_token_groups.py, SAML in test_saml_strict_validation.py, LDAP in
test_ldap_group_reading.py.
"""
import logging
from types import SimpleNamespace

import pytest

from api.v2.sso import diagnostics
from api.v2.sso.diagnostics import GroupSource, refusal_diagnosis, shown_list
from api.v2.sso.helpers import claim_groups, oidc_groups

REMEDY = 'add a role mapping rule for one of these values, or set a default role'


# ---- bounds and neutralisation ----------------------------------------------------

def test_twenty_values_of_sixty_four_characters_then_a_count():
    values = [f'g{i:02d}-' + 'x' * 100 for i in range(25)]
    text = shown_list(values)
    assert text.count("'g") == 20
    assert text.endswith('(+5 more)')
    first = text.split(', ')[0]
    assert first == repr(values[0][:63] + '…')


def test_a_short_list_has_no_count():
    assert shown_list(['a', 'b']) == "'a', 'b'"


def test_values_are_one_line_without_control_or_format_characters():
    nasty = ['a\nINJECTED: forged line', 'b\r\x1b[31m', 'c d', 'e‮f', 'g\x00']
    text = shown_list(nasty)
    for ch in ('\n', '\r', '\x1b', ' ', '‮', '\x00'):
        assert ch not in text
    assert '\\n' in text  # escaped, so the administrator still sees the exact value


def test_zero_values_say_so_and_the_remedy_is_given():
    text = refusal_diagnosis([], GroupSource('the assertion'))
    assert 'no group value was read' in text
    assert text.endswith(REMEDY)


def test_values_and_their_source_are_given():
    text = refusal_diagnosis(['pki-users'], GroupSource("SAML attribute 'groups'"))
    assert "groups read from SAML attribute 'groups': 'pki-users'" in text
    assert text.endswith(REMEDY)


def test_received_names_are_listed_only_when_nothing_was_read():
    source = GroupSource('UserInfo', candidates=['realm_access.roles'], kind='claims')
    empty = refusal_diagnosis([], source)
    assert "received claims that may carry groups: 'realm_access.roles'" in empty
    assert 'map one of them to groups in the attribute mapping' in empty
    assert 'realm_access' not in refusal_diagnosis(['x'], source)


def test_names_are_bounded_twenty_of_one_hundred_twenty_eight():
    names = [f'n{i:02d}' + 'y' * 200 for i in range(30)]
    text = refusal_diagnosis([], GroupSource('UserInfo', candidates=names, kind='claims'))
    assert text.count("'n") == 20
    assert '(+10 more)' in text
    assert repr(names[0][:127] + '…') in text


# ---- names an IdP sent that may carry groups ------------------------------------------

def test_claim_candidates_are_lists_or_group_like_names_never_values():
    claims = {
        'sub': 'SENTINEL-SUB', 'email': 'SENTINEL-MAIL', 'aud': ['ucm', 'account'],
        'memberOf': 'SENTINEL-GROUPISH', 'entitlements': ['SENTINEL-LIST'],
        'realm_access': {'roles': ['SENTINEL-ROLE']},
        'resource_access': {'ucm.example': {'roles': ['SENTINEL-CLIENT-ROLE']}},
        '_claim_names': {'groups': 'src1'},
    }
    names = diagnostics.claim_candidates(claims)
    assert names == ['memberOf', 'entitlements', 'realm_access.roles',
                     'resource_access.ucm.example.roles']
    assert not any('SENTINEL' in n for n in names)


def test_saml_candidates_show_the_friendly_name_after_the_name():
    attrs = {'urn:oid:1.3.6.1.4.1.5923.1.5.1.1': ['g1'], 'Role': ['r1'], 'email': ['e'],
             'urn:oid:2.5.4.42': ['Ann'], 'entitlement': ['a', 'b']}
    friendly = {'urn:oid:1.3.6.1.4.1.5923.1.5.1.1': 'isMemberOf', 'urn:oid:2.5.4.42': 'givenName'}
    assert diagnostics.saml_candidates(attrs, friendly) == [
        'urn:oid:1.3.6.1.4.1.5923.1.5.1.1 (isMemberOf)', 'Role', 'entitlement']


# ---- a mapping row to groups, read as a claim -----------------------------------------

@pytest.mark.parametrize('data, name, expected', [
    ({'https://example.com/groups': ['a']}, 'https://example.com/groups', ['a']),
    ({'realm_access': {'roles': ['r']}}, 'realm_access.roles', ['r']),
    ({'resource_access': {'ucm.example': {'roles': ['c']}}},
     'resource_access.ucm.example.roles', ['c']),
    ({'a.b': ['exact'], 'a': {'b': ['nested']}}, 'a.b', ['exact']),
    ({'g': 'one'}, 'g', ['one']),
    ({'g': ['ok', 3]}, 'g', []),
    ({'g': {'x': 'y'}}, 'g', []),
    ({'g': 7}, 'g', []),
    ({'other': ['a']}, 'g', []),
], ids=['exact-uri', 'dotted', 'dotted-key-with-dots', 'exact-wins', 'string',
        'mixed-list', 'object', 'number', 'absent'])
def test_claim_groups(data, name, expected):
    assert claim_groups(data, name) == expected


def test_a_mapping_row_to_groups_replaces_roles_and_groups():
    values, source = oidc_groups({'roles': ['ui-role'], 'groups': ['ui-group'], 'team': ['t1']},
                                 {'roles': ['tk-role'], 'team': ['t2']}, None, {'team': 'groups'})
    assert values == ['t2', 't1']
    assert "'team'" in source.label


def test_without_a_row_to_groups_roles_and_groups_are_read_as_before():
    values, source = oidc_groups({'roles': ['ui-role'], 'groups': ['ui-group']},
                                 {'groups': ['tk-group']}, None, {'preferred_username': 'username'})
    assert values == ['tk-group', 'ui-role', 'ui-group']
    assert 'ID token' in source.label and 'UserInfo' in source.label


def test_an_unused_token_is_neither_read_nor_listed_and_says_why():
    values, source = oidc_groups({}, {'groups': ['tk']}, 'no ID token', None)
    assert values == []
    assert 'ID token not used: no ID token' in source.label
    assert source.candidates == []


# ---- the Role resolution line ---------------------------------------------------------

def test_role_resolution_line_counts_rules_and_bounds_the_groups(app, caplog):
    from api.v2.sso.helpers import _resolve_mapped_roles
    rules = {f'rule-{i}-SECRET-RULE': 'viewer' for i in range(5)}
    provider = SimpleNamespace(provider_type='oauth2', role_mapping=rules)
    groups = [f'grp-{i}' for i in range(200)]
    with app.app_context(), caplog.at_level(logging.INFO):
        _resolve_mapped_roles(provider, {'groups': groups})
    line = next(r.getMessage() for r in caplog.records
                if r.getMessage().startswith('Role resolution'))
    assert 'SECRET-RULE' not in line
    assert '5 rule(s)' in line
    assert "'grp-19'" in line and "'grp-20'" not in line
    assert '(+180 more)' in line


def test_names_already_read_are_not_suggested_again():
    _values, source = oidc_groups({'groups': []}, {'roles': [], 'realm_access': {'roles': ['r']}},
                                  None, None)
    assert source.candidates == ['realm_access.roles']
    from api.v2.sso.helpers import saml_groups
    _values, source = saml_groups({'groups': [], 'Role': ['r']}, None)
    assert source.candidates == ['Role']


def test_ldap_group_info_line_is_bounded(monkeypatch, caplog):
    from api.v2.sso import connection_tests
    groups = [f'cn=group-{i:03d},ou=g,dc=example,dc=test' for i in range(200)]
    monkeypatch.setattr(connection_tests, '_ldap_read_groups', lambda *a, **k: groups)
    provider = SimpleNamespace(ldap_group_filter='(cn=*)', role_mapping=None, ldap_required_groups=None)
    with caplog.at_level(logging.INFO):
        result, error = connection_tests._ldap_entry_groups(provider, None, 'cn=u', 'u')
    assert result == groups and error is None
    line = next(r.getMessage() for r in caplog.records if 'LDAP groups for' in r.getMessage())
    assert 'group-019' in line and 'group-020' not in line
    assert '(+180 more)' in line
