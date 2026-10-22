"""Groups are read from SAML assertion attributes for role mapping."""
import json
from types import SimpleNamespace

import pytest

ENTRA_GROUPS = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/groups'
ENTRA_ROLE = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/role'
ENTRA_OVERAGE = 'http://schemas.microsoft.com/claims/groups.link'


@pytest.fixture
def extract(app):
    with app.app_context():
        from api.v2.sso.helpers import _extract_saml_groups
        yield _extract_saml_groups


def test_plain_groups_attribute(extract):
    assert extract({'groups': ['AMT-SG-PKI-Admins']}) == ['AMT-SG-PKI-Admins']


def test_entra_groups_and_app_roles_are_read_by_default(extract):
    attrs = {ENTRA_GROUPS: ['11111111-2222-3333-4444-555555555555'], ENTRA_ROLE: ['PKI.Admin']}
    assert extract(attrs) == ['11111111-2222-3333-4444-555555555555', 'PKI.Admin']


def test_generic_names_outside_the_defaults_are_not_read(extract):
    assert extract({'roles': ['admins'], 'memberOf': ['admins']}) == []


def test_attribute_mapped_to_groups_in_the_form_direction(extract):
    # The form saves {SSO attribute: UCM field}.
    attrs = {'groups': ['ignored'], 'MyGroups': ['wanted']}
    assert extract(attrs, {'MyGroups': 'groups', 'upn': 'username'}) == ['wanted']


def test_attribute_mapped_to_groups_in_the_reverse_direction(extract):
    attrs = {'groups': ['ignored'], 'MyGroups': ['wanted']}
    assert extract(attrs, {'groups': 'MyGroups'}) == ['wanted']


def test_configured_attribute_missing_does_not_fall_back(extract):
    assert extract({'groups': ['admins']}, {'MyGroups': 'groups'}) == []


@pytest.mark.parametrize('mapping', [
    {'groups': ['a', 'b']}, {'groups': {'x': 1}}, {'groups': 5}, {'groups': ''},
    {5: 'groups'}, ['groups'], 'groups', None,
])
def test_malformed_mapping_is_ignored_not_raised(extract, mapping):
    assert extract({'groups': ['admins']}, mapping) == ['admins']


def test_mapping_a_groups_attribute_to_another_field_is_not_a_group_source(extract):
    # {"groups": "username"} maps the SSO attribute `groups` to the username.
    assert extract({'groups': ['admins'], 'username': ['bob']}, {'groups': 'username'}) == ['admins']


def test_values_are_stripped_deduplicated_and_ordered(extract):
    attrs = {'groups': [' a ', 'b', 'a', '', None], ENTRA_GROUPS: ['b', 'c']}
    assert extract(attrs) == ['a', 'b', 'c']


def test_single_string_value(extract):
    assert extract({'groups': 'admins'}) == ['admins']


def test_no_attributes(extract):
    assert extract({}) == []
    assert extract(None) == []


def test_entra_group_overage_is_reported(extract, caplog):
    with caplog.at_level('WARNING'):
        assert extract({ENTRA_OVERAGE: ['https://graph.microsoft.com/...']}) == []
    assert 'groups.link' in caplog.text


def test_extracted_groups_resolve_a_role(app, extract):
    from api.v2.sso.helpers import _resolve_role_from_mapping
    provider = SimpleNamespace(role_mapping=json.dumps({'AMT-SG-PKI-Admins': 'admin'}))
    external = {'name_id': 'x', 'groups': extract({'groups': ['AMT-SG-PKI-Admins']})}
    with app.app_context():
        assert _resolve_role_from_mapping(provider, external) == 'admin'
