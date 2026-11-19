"""The IdP SLO URL UCM keeps from metadata is where its LogoutResponse goes by
HTTP-Redirect: ResponseLocation, else Location (SAML Metadata §2.2.2)."""
from api.v2.sso.saml_routes import _parse_saml_metadata

REDIRECT = 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect'
POST = 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST'


def _meta(*slo):
    services = ''.join(
        f'<md:SingleLogoutService Binding="{b}" Location="{loc}"'
        + (f' ResponseLocation="{resp}"' if resp else '') + '/>'
        for b, loc, resp in slo)
    return ('<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" '
            'entityID="https://idp.example/idp"><md:IDPSSODescriptor '
            'protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">'
            f'{services}<md:SingleSignOnService Binding="{REDIRECT}" Location="https://idp.example/sso"/>'
            '</md:IDPSSODescriptor></md:EntityDescriptor>')


def test_the_response_location_of_the_redirect_slo_is_kept():
    meta = _meta((REDIRECT, 'https://idp.example/slo', 'https://idp.example/slo-resp'))
    assert _parse_saml_metadata(meta)['slo_url'] == 'https://idp.example/slo-resp'


def test_without_response_location_the_location_is_kept():
    meta = _meta((POST, 'https://idp.example/slo-post', None), (REDIRECT, 'https://idp.example/slo', None))
    assert _parse_saml_metadata(meta)['slo_url'] == 'https://idp.example/slo'


def test_a_post_only_slo_is_not_kept_for_a_redirect_response():
    meta = _meta((POST, 'https://idp.example/slo-post', None))
    assert _parse_saml_metadata(meta)['slo_url'] is None
