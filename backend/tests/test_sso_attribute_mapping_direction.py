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
        mapping = {'username': 'email', 'login': 'username'}
        assert mapped_attribute(mapping, 'username', 'x') == 'login'

    def test_identity_row_is_not_a_legacy_value(self):
        # {'email': 'username'} maps the attribute "email" to the UCM username.
        assert mapped_attribute({'email': 'username'}, 'email', 'dflt') == 'dflt'

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
