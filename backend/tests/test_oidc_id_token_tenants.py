"""Microsoft Entra multi-tenant: one OIDC provider, a named list of accepted tenants.

The discovery document of a tenant-independent authority announces the issuer template
``.../{tenantid}/v2.0``; a token is accepted only when its ``tid`` is a listed GUID, its ``iss``
is that template with ``{tenantid}`` replaced by the ``tid``, and the key that signed it, when it
names an issuer, names this one. GUIDs below are invented.
"""
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.test_oidc_id_token import _Response, _rsa_jwk, _token

AUTHORITY = 'https://idp.example/organizations/v2.0'
TEMPLATE = 'https://idp.example/{tenantid}/v2.0'
DISCOVERY_URL = f'{AUTHORITY}/.well-known/openid-configuration'
JWKS_URL = 'https://idp.example/common/discovery/v2.0/keys'
TENANT_A = '0f1e2d3c-4b5a-4968-8778-a6b5c4d3e2f1'
TENANT_B = '1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d'
TENANT_C = '9e8d7c6b-5a49-4382-9170-6f5e4d3c2b1a'
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def clear_oidc_cache():
    from services.oidc_id_token import clear_oidc_cache
    clear_oidc_cache()
    yield
    clear_oidc_cache()


def _provider(**overrides):
    values = {'id': 41, 'name': 'Entra', 'oauth2_issuer': AUTHORITY, 'oauth2_client_id': 'ucm-client',
              'oauth2_jwks_uri': None, 'oauth2_tenants': f'["{TENANT_A}", "{TENANT_B}"]'}
    values.update(overrides)
    return SimpleNamespace(**values)


def _claims(tid=TENANT_A, **overrides):
    now = int(time.time())
    values = {'iss': f'https://idp.example/{tid}/v2.0', 'tid': tid, 'aud': 'ucm-client',
              'sub': 'same-subject', 'exp': now + 300, 'iat': now, 'nonce': 'n'}
    values.update(overrides)
    return values


def _serve(monkeypatch, issuer=TEMPLATE, key_issuer=None, jwks_url=JWKS_URL):
    jwk = dict(_rsa_jwk(KEY))
    if key_issuer is not None:
        jwk['issuer'] = key_issuer
    documents = {DISCOVERY_URL: {'issuer': issuer, 'jwks_uri': jwks_url}, jwks_url: {'keys': [jwk]}}
    fetched = []

    def fetch(url, **_kwargs):
        fetched.append(url)
        return _Response(documents[url])
    monkeypatch.setattr('services.oidc_id_token.safe_request_get', fetch)
    return fetched


def _verify(claims, provider=None, **kwargs):
    from services.oidc_id_token import verify_id_token
    return verify_id_token(_token(KEY, claims), provider or _provider(), 'n', **kwargs)


def _refused(claims, match, provider=None):
    from services.oidc_id_token import OIDCValidationError
    with pytest.raises(OIDCValidationError, match=match):
        _verify(claims, provider)


@pytest.mark.parametrize('tid', [TENANT_A, TENANT_B])
def test_a_listed_tenant_is_accepted(monkeypatch, tid):
    _serve(monkeypatch)
    assert _verify(_claims(tid))['tid'] == tid


def test_a_tenant_not_listed_is_refused(monkeypatch):
    _serve(monkeypatch)
    _refused(_claims(TENANT_C), f'tenant {TENANT_C} is not accepted')


def test_a_removed_tenant_is_refused(monkeypatch):
    _serve(monkeypatch)
    _refused(_claims(TENANT_B), 'is not accepted', _provider(oauth2_tenants=f'["{TENANT_A}"]'))


def test_the_issuer_of_another_tenant_with_a_listed_tid_is_refused(monkeypatch):
    _serve(monkeypatch)
    _refused(_claims(TENANT_A, iss=f'https://idp.example/{TENANT_C}/v2.0'), 'issuer mismatch')


def test_an_issuer_on_another_host_is_refused(monkeypatch):
    _serve(monkeypatch)
    _refused(_claims(TENANT_A, iss=f'https://evil.example/{TENANT_A}/v2.0'), 'issuer mismatch')


@pytest.mark.parametrize('tid', [None, 42, ['x'], '', 'not-a-guid', '{tenantid}',
                                 f'{{{TENANT_A}}}', f'{TENANT_A}/x', f'x/{TENANT_A}',
                                 f'{TENANT_A}\n', TENANT_A.replace('-', '')],
                         ids=['absent', 'number', 'list', 'empty', 'word', 'placeholder',
                              'braces', 'slash-after', 'slash-before', 'newline', 'no-dashes'])
def test_a_tid_that_is_not_a_guid_string_is_refused(monkeypatch, tid):
    _serve(monkeypatch)
    claims = _claims(TENANT_A)
    if tid is None:
        del claims['tid']
    else:
        claims['tid'] = tid
        if isinstance(tid, str):
            claims['iss'] = TEMPLATE.replace('{tenantid}', tid)
    _refused(claims, 'tenant id')


def test_a_key_whose_issuer_names_another_tenant_is_refused(monkeypatch):
    _serve(monkeypatch, key_issuer=f'https://idp.example/{TENANT_B}/v2.0')
    _refused(_claims(TENANT_A), 'JWKS key issuer')


@pytest.mark.parametrize('key_issuer', [TEMPLATE, f'https://idp.example/{TENANT_A}/v2.0'],
                         ids=['template', 'this-tenant'])
def test_a_key_whose_issuer_matches_the_token_is_accepted(monkeypatch, key_issuer):
    _serve(monkeypatch, key_issuer=key_issuer)
    assert _verify(_claims(TENANT_A))['tid'] == TENANT_A


@pytest.mark.parametrize('key_issuer', [42, '', 'https://idp.example/{TenantId}/v2.0'],
                         ids=['number', 'empty', 'other-case'])
def test_a_key_issuer_that_does_not_name_the_token_issuer_is_refused(monkeypatch, key_issuer):
    _serve(monkeypatch, key_issuer=key_issuer)
    _refused(_claims(TENANT_A), 'JWKS key issuer')


def test_a_discovery_without_template_refuses_the_configuration(monkeypatch):
    _serve(monkeypatch, issuer=AUTHORITY)
    _refused(_claims(TENANT_A), 'not a {tenantid} template')


@pytest.mark.parametrize('issuer', ['https://evil.example/{tenantid}/v2.0',
                                    'https://idp.example/{tenantid}/{tenantid}/v2.0',
                                    'https://idp.example/{tenantid}/v1.0',
                                    'https://idp.example/x{tenantid}/v2.0', 42],
                         ids=['other-host', 'twice', 'other-path', 'not-a-segment', 'number'])
def test_a_template_that_is_not_the_configured_authority_is_refused(monkeypatch, issuer):
    _serve(monkeypatch, issuer=issuer)
    _refused(_claims(TENANT_A), 'not a {tenantid} template')


def test_a_template_standing_for_more_than_one_path_segment_is_refused(monkeypatch):
    _serve(monkeypatch)
    nested = 'https://idp.example/organizations/extra/v2.0'
    documents = {f'{nested}/.well-known/openid-configuration': {'issuer': TEMPLATE, 'jwks_uri': JWKS_URL}}
    monkeypatch.setattr('services.oidc_id_token.safe_request_get',
                        lambda url, **_k: _Response(documents[url]))
    _refused(_claims(TENANT_A), 'not a {tenantid} template', _provider(oauth2_issuer=nested))


def test_the_template_comes_from_discovery_even_with_a_configured_jwks_uri(monkeypatch):
    fetched = _serve(monkeypatch, jwks_url='https://idp.example/keys')
    provider = _provider(oauth2_jwks_uri='https://idp.example/keys')
    assert _verify(_claims(TENANT_A), provider)['tid'] == TENANT_A
    assert DISCOVERY_URL in fetched


def test_the_other_checks_still_apply(monkeypatch):
    _serve(monkeypatch)
    _refused(_claims(TENANT_A, aud='other-client'), 'audience mismatch')
    _refused(_claims(TENANT_A, nonce='other'), 'nonce mismatch')
    _refused(_claims(TENANT_A, exp=int(time.time()) - 3600), 'expired')
    _refused(_claims(TENANT_A, azp='other-client'), 'authorized party')


@pytest.mark.parametrize('stored', ['not json', '{"a": 1}', '["not-a-guid"]', '[42]'])
def test_unreadable_stored_tenants_refuse_every_token(monkeypatch, stored):
    _serve(monkeypatch)
    _refused(_claims(TENANT_A), 'accepted tenants', _provider(oauth2_tenants=stored))


def test_compatibility_mode_is_refused_with_tenants(monkeypatch):
    from services.oidc_id_token import OIDCValidationError, unverified_claims_error, verify_id_token
    _serve(monkeypatch)
    with pytest.raises(OIDCValidationError, match='require ID token verification'):
        verify_id_token(_token(KEY, _claims(TENANT_A)), _provider(), 'n', verify=False)
    assert 'require ID token verification' in unverified_claims_error(_claims(TENANT_A), _provider(), 'n')


@pytest.mark.parametrize('stored', [None, '', '[]'])
def test_without_tenants_a_template_discovery_is_still_a_mismatch(monkeypatch, stored):
    """A provider without tenants keeps the exact issuer match of OIDC Core §3.1.3.7 step 2."""
    _serve(monkeypatch)
    _refused(_claims(TENANT_A), 'OIDC discovery issuer mismatch', _provider(oauth2_tenants=stored))


def test_normalize_tenants_lowers_dedups_and_refuses_anything_else():
    from services.oidc_id_token import normalize_tenants
    upper = TENANT_A.upper()
    assert normalize_tenants([upper, TENANT_A, f' {TENANT_B} ']) == [TENANT_A, TENANT_B]
    assert normalize_tenants(f'{TENANT_A}, {TENANT_B}\n{TENANT_C}') == [TENANT_A, TENANT_B, TENANT_C]
    assert normalize_tenants([]) == [] and normalize_tenants(None) == [] and normalize_tenants('') == []
    for bad in (['*'], ['common'], ['organizations'], [42], 42, {'a': 1}, [f'{{{TENANT_A}}}']):
        with pytest.raises(ValueError):
            normalize_tenants(bad)


def test_a_discovery_cached_for_one_issuer_does_not_serve_tenants(monkeypatch):
    """The template rule holds for the document used, cached ones included (another node's cache)."""
    _serve(monkeypatch, issuer=AUTHORITY)
    single = _provider(oauth2_tenants=None)
    assert _verify(_claims(TENANT_A, iss=AUTHORITY), single)['tid'] == TENANT_A
    _refused(_claims(TENANT_A, iss=AUTHORITY), 'not a {tenantid} template')
