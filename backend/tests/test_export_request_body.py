"""Exports that may return a private key read their options by allow-list.

A GET takes them from the query string and carries no body; a POST takes them
from a JSON object body and nothing in the query string. A name the route does
not declare, a value of another type and an unknown format answer 400, so no
password, under any name or in any place, is ignored while a key leaves in clear.
"""
import io
import json

import pytest

from tests.test_key_recovery import _open_request, _set_dual_control
from tests.test_mtls_pem_chain import enrolled  # noqa: F401
from tests.test_user_certificate_key_export_guard import _enrolment_for

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates', 'drop_new_users',
                                     'dual_control_at_its_default')

PASSWORD = 'Passw0rd!2026'
SECRET = 'Sup3rSecretValue!'
ROUTES = ['certificate', 'ca', 'user_certificate', 'csr', 'mtls', 'key_recovery']
GET_ROUTES = [r for r in ROUTES if r != 'key_recovery']
# A format that carries a private key on each route (none to choose on key recovery)
KEY_FORMAT = {'certificate': 'key', 'ca': 'key', 'user_certificate': 'key', 'csr': 'key',
              'mtls': 'p12', 'key_recovery': None}
# The options each route reads, and nothing else
DECLARED = {
    'certificate': {'format', 'include_key', 'include_chain', 'include_root', 'password',
                    'legacy', 'chain_variant'},
    'ca': {'format', 'include_key', 'include_chain', 'password', 'legacy', 'chain_variant'},
    'user_certificate': {'format', 'include_key', 'include_chain', 'include_root', 'password',
                         'legacy', 'chain_variant'},
    'csr': {'format', 'password'},
    'mtls': {'format', 'password', 'include_chain', 'include_root', 'legacy'},
    'key_recovery': {'password', 'legacy'},
}


def _declared_options(kind):
    if kind == 'certificate':
        from api.v2.certificates.export import EXPORT_OPTIONS
    elif kind == 'ca':
        from api.v2.cas.export import EXPORT_OPTIONS
    elif kind == 'user_certificate':
        from api.v2.user_certificates import EXPORT_OPTIONS
    elif kind == 'csr':
        from api.v2.csrs import EXPORT_OPTIONS
    elif kind == 'mtls':
        from api.v2.mtls import DOWNLOAD_OPTIONS as EXPORT_OPTIONS
    else:
        from api.v2.key_recovery import RECOVER_OPTIONS as EXPORT_OPTIONS
    return EXPORT_OPTIONS


def _csr_route(auth_client, cn):
    r = auth_client.post('/api/v2/csrs', json={
        'cn': cn, 'organization': 'O', 'country': 'US', 'key_type': 'RSA 2048'})
    assert r.status_code == 201, r.data[:200]
    return f"/api/v2/csrs/{r.get_json()['data']['id']}/export"


def _recovery_route(app, auth_client, create_cert):
    _set_dual_control(app, False)
    rid = _open_request(auth_client, create_cert(cn='body-rule-recovery.example.com')['id'])
    assert auth_client.post(f'/api/v2/key-recovery/{rid}/approve', json={}).status_code == 200
    return f'/api/v2/key-recovery/{rid}/recover'


def _route(kind, request, app, auth_client, create_ca, create_cert, create_user):
    if kind == 'certificate':
        return f"/api/v2/certificates/{create_cert(cn='body-rule.example.com')['id']}/export"
    if kind == 'ca':
        return f"/api/v2/cas/{create_ca(cn='Body Rule CA')['id']}/export"
    if kind == 'user_certificate':
        create_user(username='body_rule_owner', role='viewer')
        rid, _ = _enrolment_for(app, create_cert, 'body_rule_owner', 'body-rule-user')
        return f'/api/v2/user-certificates/{rid}/export'
    if kind == 'csr':
        return _csr_route(auth_client, 'body-rule-csr.example.com')
    if kind == 'mtls':
        return request.getfixturevalue('enrolled')
    return _recovery_route(app, auth_client, create_cert)


@pytest.fixture(params=ROUTES)
def route(request, app, auth_client, create_ca, create_cert, create_user):
    return request.param, _route(request.param, request, app, auth_client,
                                 create_ca, create_cert, create_user)


@pytest.fixture(params=GET_ROUTES)
def get_route(request, app, auth_client, create_ca, create_cert, create_user):
    return request.param, _route(request.param, request, app, auth_client,
                                 create_ca, create_cert, create_user)


def _key_body(kind, **extra):
    body = {} if KEY_FORMAT[kind] is None else {'format': KEY_FORMAT[kind]}
    return {**body, **extra}


def _refused(r, *fragments):
    assert r.status_code == 400, r.data[:300]
    assert b'PRIVATE KEY' not in r.data
    assert SECRET.encode() not in r.data and PASSWORD.encode() not in r.data
    message = r.get_json()['message']
    for fragment in fragments:
        assert fragment in message, message


# The requests of the review, CSR route first: each returned the key in clear

def test_csr_get_with_a_form_password_in_its_body_is_refused(auth_client):
    url = _csr_route(auth_client, 'get-body-csr.example.com')
    r = auth_client.open(f'{url}?format=key', method='GET', data={'password': PASSWORD})
    _refused(r, 'GET export carries no body')


def test_csr_get_with_a_json_password_in_its_body_is_refused(auth_client):
    url = _csr_route(auth_client, 'get-json-csr.example.com')
    r = auth_client.open(f'{url}?format=key', method='GET', json={'password': PASSWORD})
    _refused(r, 'GET export carries no body')


def test_csr_get_with_a_capitalised_password_in_the_query_is_refused(auth_client):
    url = _csr_route(auth_client, 'get-cap-csr.example.com')
    _refused(auth_client.get(f'{url}?format=key&Password={SECRET}'), 'Unknown export option: Password')


@pytest.mark.parametrize('body', [
    {'passphrase': SECRET}, {'Password': SECRET}, {'pkcs12_password': SECRET},
    {'options': {'password': SECRET}},
])
def test_csr_json_password_under_another_name_is_refused(auth_client, body):
    url = _csr_route(auth_client, 'json-name-csr.example.com')
    r = auth_client.post(url, json={'format': 'key', **body})
    _refused(r, f'Unknown export option: {next(iter(body))}')


def test_csr_post_with_its_format_in_the_query_string_is_refused(auth_client):
    url = _csr_route(auth_client, 'post-query-csr.example.com')
    _refused(auth_client.post(f'{url}?format=key', json={}), 'not the query string', 'format')


# The same rules on every route

def test_get_with_a_body_is_refused(auth_client, get_route):
    kind, url = get_route
    _refused(auth_client.open(url, method='GET', data={'format': KEY_FORMAT[kind], 'password': PASSWORD}),
             'GET export carries no body')


def test_get_with_a_chunked_body_is_refused(auth_client, get_route):
    _kind, url = get_route
    r = auth_client.open(url, method='GET', input_stream=io.BytesIO(f'password={PASSWORD}'.encode()),
                         content_type='application/x-www-form-urlencoded',
                         headers={'Transfer-Encoding': 'chunked'},
                         environ_overrides={'wsgi.input_terminated': True})
    _refused(r, 'GET export carries no body')


def test_post_form_body_is_refused(auth_client, route):
    kind, url = route
    _refused(auth_client.post(url, data=_key_body(kind, password=PASSWORD)), 'JSON body holding an object')


def test_post_plain_text_body_is_refused(auth_client, route):
    kind, url = route
    r = auth_client.post(url, data=json.dumps(_key_body(kind, password=PASSWORD)),
                         content_type='text/plain')
    _refused(r, 'JSON body holding an object')


def test_post_without_a_body_is_refused(auth_client, route):
    _kind, url = route
    _refused(auth_client.post(url), 'JSON body holding an object')


@pytest.mark.parametrize('raw', ['null', '[]', '[1]', '"key"', '3'])
def test_json_body_that_is_not_an_object_is_refused(auth_client, route, raw):
    _kind, url = route
    _refused(auth_client.post(url, data=raw, content_type='application/json'), 'JSON body holding an object')


def test_password_in_the_query_string_is_refused(auth_client, route):
    kind, url = route
    _refused(auth_client.post(f'{url}?password={PASSWORD}', json=_key_body(kind)), 'query string')


def test_password_in_the_query_string_of_a_get_is_refused(auth_client, get_route):
    _kind, url = get_route
    _refused(auth_client.get(f'{url}?password={PASSWORD}'), 'query string')


def test_any_query_option_on_a_post_is_refused(auth_client, route):
    kind, url = route
    _refused(auth_client.post(f'{url}?include_chain=true', json=_key_body(kind, password=PASSWORD)),
             'not the query string', 'include_chain')


def test_an_unknown_name_is_refused_without_its_value(auth_client, route):
    kind, url = route
    _refused(auth_client.post(url, json=_key_body(kind, passphrase=SECRET)),
             'Unknown export option: passphrase')


def test_an_unknown_query_name_is_refused(auth_client, get_route):
    _kind, url = get_route
    _refused(auth_client.get(f'{url}?Password={SECRET}'), 'Unknown export option: Password')


def test_a_post_only_option_in_the_query_of_a_get_is_refused(auth_client, get_route):
    kind, url = get_route
    if 'legacy' not in DECLARED[kind]:
        pytest.skip('no legacy option on this route')
    _refused(auth_client.get(f'{url}?legacy=true'), 'legacy is read from a POST JSON body only')


def test_a_repeated_query_option_is_refused(auth_client, get_route):
    _kind, url = get_route
    _refused(auth_client.get(f'{url}?format=pem&format=key'), 'format is given more than once')


@pytest.mark.parametrize('value', [5, None, True, ['key']])
def test_a_format_of_another_type_is_refused(auth_client, route, value):
    kind, url = route
    if 'format' not in DECLARED[kind]:
        pytest.skip('no format option on this route')
    _refused(auth_client.post(url, json={'format': value}), 'format must be a string')


def test_an_unknown_format_is_refused(auth_client, route):
    kind, url = route
    if 'format' not in DECLARED[kind]:
        pytest.skip('no format option on this route')
    _refused(auth_client.post(url, json={'format': 'nope', 'password': PASSWORD}), 'format must be one of')


@pytest.mark.parametrize('value', [5, False, ['x']])
def test_a_password_of_another_type_is_refused(auth_client, route, value):
    kind, url = route
    _refused(auth_client.post(url, json=_key_body(kind, password=value)), 'password must be a string')


def test_a_json_boolean_option_must_be_a_boolean(auth_client, route):
    kind, url = route
    if 'legacy' not in DECLARED[kind]:
        pytest.skip('no boolean option on this route')
    _refused(auth_client.post(url, json=_key_body(kind, password=PASSWORD, legacy='true')),
             'legacy must be a boolean')


def test_a_query_boolean_option_must_be_true_or_false(auth_client, get_route):
    kind, url = get_route
    if 'include_chain' not in DECLARED[kind]:
        pytest.skip('no boolean option in this route query')
    _refused(auth_client.get(f'{url}?include_chain=yes'), 'include_chain must be true or false')


def test_a_text_option_must_be_a_string(auth_client, route):
    kind, url = route
    if 'chain_variant' not in DECLARED[kind]:
        pytest.skip('no text option on this route')
    _refused(auth_client.post(url, json={'format': 'pem', 'chain_variant': 5}),
             'chain_variant must be a string')


# Each route declares exactly its options, and accepts each of them

def test_each_route_declares_exactly_its_options(route):
    kind, _url = route
    assert set(_declared_options(kind)) == DECLARED[kind]


def test_each_declared_option_is_read(auth_client, route):
    kind, url = route
    values = {'format': KEY_FORMAT[kind] or 'pem', 'include_key': False, 'include_chain': False,
              'include_root': False, 'password': PASSWORD, 'legacy': False, 'chain_variant': 'auto'}
    body = {name: values[name] for name in DECLARED[kind]}
    r = auth_client.post(url, json=body)
    assert r.status_code == 200, r.data[:300]


# Left as they were

def test_get_of_the_certificate_alone_still_works(auth_client, get_route):
    kind, url = get_route
    r = auth_client.get(url if kind == 'csr' else f'{url}?format=pem')
    assert r.status_code == 200, r.data[:300]
    assert b'PRIVATE KEY' not in r.data
    assert b'-----BEGIN' in r.data


def test_csr_get_of_the_key_without_a_password_still_works(auth_client):
    url = _csr_route(auth_client, 'get-key-csr.example.com')
    r = auth_client.get(f'{url}?format=key')
    assert r.status_code == 200, r.data[:300]
    assert b'PRIVATE KEY' in r.data


def test_json_body_still_exports_the_protected_key(auth_client, route):
    kind, url = route
    r = auth_client.post(url, json=_key_body(kind, password=PASSWORD))
    assert r.status_code == 200, r.data[:300]
    if kind in ('mtls', 'key_recovery'):
        assert r.mimetype == 'application/x-pkcs12'
    else:
        assert b'ENCRYPTED PRIVATE KEY' in r.data


@pytest.mark.parametrize('fmt', ['PKCS12', 'pfx', 'p12'])
def test_mtls_pkcs12_spellings(auth_client, enrolled, fmt):  # noqa: F811
    r = auth_client.post(enrolled, json={'format': fmt, 'password': PASSWORD})
    assert r.status_code == 200, r.data[:300]
    assert r.mimetype == 'application/x-pkcs12'


@pytest.mark.parametrize('fmt', ['der', 'jks'])
def test_mtls_unknown_format_is_refused(auth_client, enrolled, fmt):  # noqa: F811
    _refused(auth_client.get(f'{enrolled}?format={fmt}'), 'format must be one of')


# A JSON name given twice: the last one used to win, and a trailing null read as no password

@pytest.mark.parametrize('repeat', ['null', '""'])
def test_a_repeated_json_name_is_refused(auth_client, route, repeat):
    kind, url = route
    fmt = f'"format": "{KEY_FORMAT[kind]}", ' if KEY_FORMAT[kind] else ''
    body = '{%s"password": "%s", "password": %s}' % (fmt, PASSWORD, repeat)
    _refused(auth_client.post(url, data=body, content_type='application/json'),
             'password is given more than once')


def test_a_repeated_name_inside_a_nested_object_is_refused(auth_client, route):
    _kind, url = route
    body = '{"options": {"x": "%s", "x": null}}' % SECRET
    _refused(auth_client.post(url, data=body, content_type='application/json'),
             'x is given more than once')


@pytest.mark.parametrize('raw, fragment', [
    (b'', 'JSON body holding an object'),
    (b'{"format": ', 'not valid JSON'),
    (b'{"password": "\xff\xfe"}', 'UTF-8'),
])
def test_a_body_that_is_not_utf8_json_is_refused(auth_client, route, raw, fragment):
    """Guard: what get_json refused stays refused."""
    _kind, url = route
    _refused(auth_client.post(url, data=raw, content_type='application/json'), fragment)


def test_a_byte_order_mark_is_ignored_and_the_body_still_checked(auth_client, route):
    """RFC 8259 section 8.1 lets a parser ignore the mark: the body is read, so its repeated name is seen."""
    _kind, url = route
    body = b'\xef\xbb\xbf' + ('{"password": "%s", "password": null}' % PASSWORD).encode()
    _refused(auth_client.post(url, data=body, content_type='application/json'),
             'password is given more than once')


def test_a_body_nested_past_the_parser_depth_is_a_400(auth_client, route):
    _kind, url = route
    depth = 100000
    body = '{"x": ' + '[' * depth + ']' * depth + '}'
    _refused(auth_client.post(url, data=body, content_type='application/json'), 'not valid JSON')


def test_the_body_size_limit_still_applies(app, auth_client, route, monkeypatch):
    """Guard: the raw body is read through the request stream, which the limit bounds."""
    kind, url = route
    monkeypatch.setitem(app.config, 'MAX_CONTENT_LENGTH', 64)
    body = json.dumps(_key_body(kind, password=PASSWORD + 'x' * 100))
    r = auth_client.post(url, data=body, content_type='application/json')
    assert r.status_code == 413, r.data[:300]
    assert b'PRIVATE KEY' not in r.data


# A HEAD is answered like a GET: it never decrypts a key nor writes an export audit line

def _audit_count(app):
    from models.audit_log import AuditLog
    with app.app_context():
        return AuditLog.query.count()


def test_head_asking_for_a_key_is_refused_and_audits_nothing(app, auth_client, get_route):
    kind, url = get_route
    before = _audit_count(app)
    fmt = 'pkcs12' if kind == 'mtls' else 'key'
    r = auth_client.head(f'{url}?format={fmt}')
    assert r.status_code == 400, r.status_code
    assert _audit_count(app) == before


# No password: null and "" read as none, a key in clear where that is wanted, a refusal where one is needed

@pytest.mark.parametrize('empty', [None, ''])
@pytest.mark.parametrize('kind_body', [
    ('certificate', {'format': 'key'}), ('certificate', {'format': 'pem', 'include_key': True}),
    ('ca', {'format': 'key'}), ('ca', {'format': 'pem', 'include_key': True}),
    ('user_certificate', {'format': 'key'}), ('csr', {'format': 'key'}),
])
def test_an_empty_password_means_a_key_in_clear(request, app, auth_client, create_ca, create_cert,
                                                create_user, kind_body, empty):
    kind, body = kind_body
    url = _route(kind, request, app, auth_client, create_ca, create_cert, create_user)
    r = auth_client.post(url, json={**body, 'password': empty})
    assert r.status_code == 200, r.data[:300]
    assert b'PRIVATE KEY' in r.data and b'ENCRYPTED PRIVATE KEY' not in r.data


@pytest.mark.parametrize('empty', [None, ''])
@pytest.mark.parametrize('kind_fmt', [
    ('certificate', 'pkcs12'), ('certificate', 'jks'), ('ca', 'pkcs12'), ('ca', 'jks'),
    ('user_certificate', 'pkcs12'), ('user_certificate', 'jks'), ('mtls', 'pkcs12'), ('key_recovery', None),
])
def test_an_empty_password_is_refused_where_one_is_needed(request, app, auth_client, create_ca,
                                                         create_cert, create_user, kind_fmt, empty):
    kind, fmt = kind_fmt
    url = _route(kind, request, app, auth_client, create_ca, create_cert, create_user)
    body = {'password': empty} if fmt is None else {'format': fmt, 'password': empty}
    r = auth_client.post(url, json=body)
    assert r.status_code == 400, r.data[:300]
    assert b'PRIVATE KEY' not in r.data


# Query booleans and messages

def test_a_query_boolean_ignores_case_but_not_spaces(auth_client, get_route):
    kind, url = get_route
    if kind == 'csr':
        pytest.skip('no boolean option in this route query')
    assert auth_client.get(f'{url}?format=pem&include_chain=TRUE').status_code == 200
    _refused(auth_client.get(f'{url}?format=pem&include_chain=%20true'), 'include_chain must be true or false')


def test_a_long_unknown_name_is_cut_in_the_message(auth_client, route):
    _kind, url = route
    name = 'n' * 64 + 'TAIL'
    r = auth_client.post(url, json={name: 1})
    _refused(r, 'Unknown export option: ' + 'n' * 64)
    assert 'TAIL' not in r.get_json()['message']


def test_an_empty_name_has_its_own_message(auth_client, get_route):
    _kind, url = get_route
    _refused(auth_client.get(f'{url}?=x'), 'An export option has an empty name')


def test_an_empty_format_has_its_own_message(auth_client, get_route):
    _kind, url = get_route
    r = auth_client.get(f'{url}?format=')
    _refused(r, 'format is empty')
    assert ' :' not in r.get_json()['message']
