"""Attribute Mapping is stored as {SSO attribute: UCM field} by the form; the
legacy {UCM field: SSO attribute} shape keeps working. Both reach OIDC and SAML."""
import pytest

from api.v2.sso.helpers import (mapped_attribute, oidc_identity, saml_identity)

FORM = {'upn': 'username', 'mail': 'email', 'displayName': 'fullname'}
LEGACY = {'username': 'upn', 'email': 'mail', 'fullname': 'displayName'}


class TestMappedAttribute:
    def test_form_direction(self):
        assert mapped_attribute(FORM, 'username', 'x') == 'upn'

    def test_legacy_direction(self):
        assert mapped_attribute(LEGACY, 'email', 'x') == 'mail'

    def test_form_direction_wins_over_legacy(self):
        mapping = {'upn': 'username', 'username': 'login'}
        assert mapped_attribute(mapping, 'username', 'x') == 'upn'

    def test_field_to_field_row_reads_the_legacy_way_by_default(self):
        # {'username': 'email'} was the only shape that ever worked: username <- email.
        assert mapped_attribute({'username': 'email'}, 'username', 'dflt') == 'email'
        assert mapped_attribute({'username': 'email'}, 'email', 'dflt') == 'dflt'

    def test_field_to_field_row_follows_the_attributes_present(self):
        # The form's {'email': 'username'}: the assertion has "email", not "username".
        present = {'email': 'a@corp.example'}
        assert mapped_attribute({'email': 'username'}, 'username', 'dflt', present) == 'email'
        assert mapped_attribute({'email': 'username'}, 'email', 'dflt', present) == 'dflt'
        # The legacy {'username': 'email'} with the same assertion stays legacy.
        assert mapped_attribute({'username': 'email'}, 'username', 'dflt', present) == 'email'

    @pytest.mark.parametrize('bad', [None, [], 'text', 5, {}, {'upn': None},
                                     {'upn': 3}, {'': 'username'}, {'username': ''},
                                     {'username': ['a']}, {'username': 7}])
    def test_malformed_falls_back_to_default(self, bad):
        assert mapped_attribute(bad, 'username', 'dflt') == 'dflt'


class TestOidcIdentity:
    INFO = {'upn': 'alice', 'mail': 'a@x.org', 'displayName': 'Alice A',
            'preferred_username': 'pu', 'email': 'e@x.org', 'name': 'N'}

    @pytest.mark.parametrize('mapping', [FORM, LEGACY])
    def test_both_directions(self, mapping):
        assert oidc_identity(self.INFO, mapping) == ('alice', 'a@x.org', 'Alice A')

    def test_defaults_without_mapping(self):
        assert oidc_identity(self.INFO, {}) == ('pu', 'e@x.org', 'N')

    def test_username_falls_back_to_email_local_part(self):
        assert oidc_identity({'email': 'bob@x.org'}, FORM)[0] == 'bob'

    def test_malformed_mapping_and_userinfo(self):
        assert oidc_identity({'preferred_username': 'u'}, ['x'])[0] == 'u'
        assert oidc_identity({'upn': None, 'email': None}, FORM) == ('', '', '')


class TestSamlIdentity:
    ATTRS = {'upn': ['alice'], 'mail': ['a@x.org'], 'displayName': ['Alice A'],
             'username': ['dflt-u'], 'email': ['dflt@x.org'], 'name': ['Dflt']}

    @pytest.mark.parametrize('mapping', [FORM, LEGACY])
    def test_both_directions(self, mapping):
        assert saml_identity(self.ATTRS, 'nid', mapping) == ('alice', 'a@x.org', 'Alice A')

    def test_defaults_and_name_id_fallback(self):
        assert saml_identity(self.ATTRS, 'nid', {}) == ('dflt-u', 'dflt@x.org', 'Dflt')
        assert saml_identity({}, 'nid', FORM) == ('nid', '', '')

    def test_malformed_values(self):
        attrs = {'upn': [], 'mail': [None], 'displayName': 'str'}
        assert saml_identity(attrs, 'nid', FORM) == ('nid', '', 'str')
        assert saml_identity(None, 'nid', 'bad') == ('nid', '', '')

    def test_non_string_value_does_not_crash(self):
        assert saml_identity({'upn': [5], 'mail': [['x']]}, 'nid', FORM) == ('nid', '', '')


class TestLegacyFieldToFieldRow:
    """A stored {'username': 'email'} keeps deriving the same identity (review of #408)."""

    def test_oidc(self):
        info = {'sub': 's1', 'email': 'alice@corp.example', 'name': 'Alice'}
        assert oidc_identity(info, {'username': 'email'}) == \
            ('alice@corp.example', 'alice@corp.example', 'Alice')

    def test_saml(self):
        attrs = {'email': ['alice@corp.example']}
        assert saml_identity(attrs, 'opaque-nameid', {'username': 'email'})[:2] == \
            ('alice@corp.example', 'alice@corp.example')

    def test_saml_form_row_with_field_names(self):
        attrs = {'email': ['bob@corp.example']}
        assert saml_identity(attrs, 'opaque-nameid', {'email': 'username'})[0] == 'bob@corp.example'

    def test_oidc_form_row_with_field_names(self):
        info = {'sub': 's2', 'email': 'bob@corp.example'}
        assert oidc_identity(info, {'email': 'username'})[0] == 'bob@corp.example'
