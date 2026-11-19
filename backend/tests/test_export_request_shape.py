"""An export route that may return a private key reads its request in one shape.

A body is accepted only from a POST, as a JSON object, with its JSON content
type; `password` is a string or null; a name is not repeated; and a name that
looks like a password is refused wherever the route would not read it. Before,
a password sent as a form, with a GET, as a number or as `Password` was ignored
and the key came back in clear.
"""
import base64
import io
import json

import pytest

from models import db

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

PASSWORD = 'Passw0rd!2026'
SECRET = 'Sup3rSecretValue!'

# route -> (format that carries a key, accepts GET)
KEY_ROUTES = {
    'certificate': ('key', True),
    'ca': ('key', True),
    'user_certificate': ('pem', True),
    'csr': ('key', True),
    'mtls': ('pkcs12', True),
    'key_recovery': (None, False),
}
OTHER_ROUTES = ['certificates_all', 'cas_all']
# A format each route encrypts with a password (section 6 covers the PEM of the first three)
PROTECTED_FORMAT = {'certificate': 'key', 'ca': 'key', 'user_certificate': 'pkcs12', 'csr': 'key',
                    'mtls': 'pkcs12', 'key_recovery': None}
ALL_ROUTES = list(KEY_ROUTES) + OTHER_ROUTES
GET_ROUTES = [k for k, (_, get) in KEY_ROUTES.items() if get] + OTHER_ROUTES


@pytest.fixture(scope='module')
def material(app, create_ca, create_cert, auth_client):
    from models import Certificate, User
    from models.auth_certificate import AuthCertificate
    ca = create_ca(cn='Export shape CA')
    cert = create_cert(cn='export-shape.example.com')
    csr = auth_client.post('/api/v2/csrs', json={
        'cn': 'export-shape-csr.example.com', 'organization': 'O', 'country': 'US',
        'key_type': 'RSA 2048'})
    assert csr.status_code == 201, csr.data[:200]
    with app.app_context():
        row = db.session.get(Certificate, cert['id'])
        admin = User.query.filter_by(username='admin').first()
        enrolment = AuthCertificate(
            user_id=admin.id, cert_serial=row.serial_number,
            cert_pem=base64.b64decode(row.crt),
            cert_subject=row.subject or 'CN=export-shape.example.com',
            cert_issuer=row.issuer, cert_fingerprint='', name='export-shape', enabled=True)
        db.session.add(enrolment)
        db.session.commit()
        enrolment_id = enrolment.id
    yield {'ca': ca['id'], 'cert': cert['id'], 'enrolment': enrolment_id,
           'csr': csr.get_json()['data']['id']}
    with app.app_context():
        stale = db.session.get(AuthCertificate, enrolment_id)
        if stale:
            db.session.delete(stale)
            db.session.commit()


def _recovery_url(app, auth_client, cert_id):
    from models import SystemConfig
    with app.app_context():
        row = SystemConfig.query.filter_by(key='key_recovery_dual_control').first()
        if not row:
            row = SystemConfig(key='key_recovery_dual_control', value='')
            db.session.add(row)
        row.value = 'false'
        db.session.commit()
    r = auth_client.post(f'/api/v2/certificates/{cert_id}/key-recovery', json={'reason': 'shape'})
    assert r.status_code == 201, r.data
    rid = r.get_json()['data']['id']
    assert auth_client.post(f'/api/v2/key-recovery/{rid}/approve', json={}).status_code == 200
    return f'/api/v2/key-recovery/{rid}/recover'


def _url(kind, material, app, auth_client):
    m = material
    return {
        'certificate': f"/api/v2/certificates/{m['cert']}/export",
        'ca': f"/api/v2/cas/{m['ca']}/export",
        'user_certificate': f"/api/v2/user-certificates/{m['enrolment']}/export",
        'csr': f"/api/v2/csrs/{m['csr']}/export",
        'mtls': f"/api/v2/mtls/certificates/{m['enrolment']}/download",
        'certificates_all': '/api/v2/certificates/export',
        'cas_all': '/api/v2/cas/export',
    }.get(kind) or _recovery_url(app, auth_client, m['cert'])


@pytest.fixture(params=ALL_ROUTES)
def route(request, material, app, auth_client):
    return request.param, _url(request.param, material, app, auth_client)


@pytest.fixture(params=KEY_ROUTES)
def key_route(request, material, app, auth_client):
    return request.param, _url(request.param, material, app, auth_client)


@pytest.fixture(params=GET_ROUTES)
def get_route(request, material, app, auth_client):
    return request.param, _url(request.param, material, app, auth_client)


def _body(kind, **extra):
    fmt = KEY_ROUTES[kind][0] if kind in KEY_ROUTES else 'pem'
    return {**({} if fmt is None else {'format': fmt}), **extra}


def _protected(kind):
    fmt = PROTECTED_FORMAT[kind]
    return {**({} if fmt is None else {'format': fmt}), 'password': PASSWORD}


def _refused(r, *fragments):
    assert r.status_code == 400, r.data[:300]
    assert b'PRIVATE KEY' not in r.data
    assert SECRET.encode() not in r.data and PASSWORD.encode() not in r.data
    message = r.get_json()['message']
    assert SECRET not in message
    for fragment in fragments:
        assert fragment.lower() in message.lower(), message


def _json(client, url, raw, content_type='application/json'):
    return client.post(url, data=raw, content_type=content_type)


# 1. A body is a POST JSON object

def test_post_form_body_is_refused(auth_client, route):
    kind, url = route
    _refused(auth_client.post(url, data=_body(kind, password=PASSWORD)), 'JSON object')


def test_post_json_without_its_content_type_is_refused(auth_client, route):
    kind, url = route
    r = _json(auth_client, url, json.dumps(_body(kind, password=PASSWORD)), 'text/plain')
    _refused(r, 'JSON object')


def test_get_with_a_form_body_is_refused(auth_client, get_route):
    kind, url = get_route
    _refused(auth_client.open(url, method='GET', data=_body(kind, password=PASSWORD)), 'JSON object')


def test_get_with_a_json_body_is_refused(auth_client, get_route):
    kind, url = get_route
    _refused(auth_client.open(url, method='GET', json=_body(kind, password=PASSWORD)), 'JSON object')


def test_get_with_a_chunked_body_is_refused(auth_client, get_route):
    _kind, url = get_route
    r = auth_client.open(url, method='GET', input_stream=io.BytesIO(f'password={PASSWORD}'.encode()),
                         content_type='application/x-www-form-urlencoded',
                         headers={'Transfer-Encoding': 'chunked'},
                         environ_overrides={'wsgi.input_terminated': True})
    _refused(r, 'JSON object')


def test_head_with_a_body_is_refused(auth_client, get_route):
    kind, url = get_route
    r = auth_client.open(url, method='HEAD', json=_body(kind, password=PASSWORD))
    assert r.status_code == 400 and b'PRIVATE KEY' not in r.data


@pytest.mark.parametrize('raw', ['null', '[]', '[1]', '"key"', '3', 'true'])
def test_json_that_is_not_an_object_is_refused(auth_client, route, raw):
    _kind, url = route
    _refused(_json(auth_client, url, raw), 'JSON object')


@pytest.mark.parametrize('raw, fragment', [
    (b'{"format": ', 'not valid JSON'),
    (b'{"password": "\xff\xfe"}', 'UTF-8'),
])
def test_invalid_or_non_utf8_json_is_refused(auth_client, route, raw, fragment):
    _kind, url = route
    _refused(_json(auth_client, url, raw), fragment)


def test_a_body_nested_past_the_parser_depth_is_a_400(auth_client, route):
    _kind, url = route
    depth = 100000
    _refused(_json(auth_client, url, '{"x": ' + '[' * depth + ']' * depth + '}'), 'not valid JSON')


def test_a_byte_order_mark_is_ignored_and_the_body_still_read(auth_client, key_route):
    kind, url = key_route
    raw = b'\xef\xbb\xbf' + json.dumps(_protected(kind)).encode()
    r = _json(auth_client, url, raw)
    assert r.status_code == 200, r.data[:300]
    assert b'-----BEGIN' not in r.data or b'ENCRYPTED PRIVATE KEY' in r.data


def test_a_byte_order_mark_does_not_hide_a_repeated_name(auth_client, key_route):
    kind, url = key_route
    raw = b'\xef\xbb\xbf' + ('{"password": "%s", "password": null}' % PASSWORD).encode()
    _refused(_json(auth_client, url, raw), 'more than once')


# 2. password is a string or null

@pytest.mark.parametrize('value', [0, False, True, 5, [], {}, ['x'], {'a': 1}])
def test_a_password_of_another_type_is_refused(auth_client, key_route, value):
    kind, url = key_route
    _refused(auth_client.post(url, json=_body(kind, password=value)), 'password must be a string')


# 3. A name is not repeated

@pytest.mark.parametrize('repeat', ['null', '""', '0'])
def test_a_repeated_json_name_is_refused(auth_client, route, repeat):
    kind, url = route
    fmt = f'"format": "{KEY_ROUTES[kind][0]}", ' if kind in KEY_ROUTES and KEY_ROUTES[kind][0] else ''
    raw = '{%s"password": "%s", "password": %s}' % (fmt, PASSWORD, repeat)
    _refused(_json(auth_client, url, raw), 'more than once')


def test_a_repeated_name_inside_a_nested_object_is_refused(auth_client, route):
    _kind, url = route
    _refused(_json(auth_client, url, '{"o": {"x": "%s", "x": null}}' % SECRET), 'more than once')


# 4. A password-looking name where the route does not read it

@pytest.mark.parametrize('body', [
    {'Password': SECRET}, {'passphrase': SECRET}, {'pkcs12_password': SECRET},
    {'PASSWORD': SECRET}, {'options': {'password': SECRET}}, {'a': [{'Passphrase': SECRET}]},
])
def test_a_password_under_another_name_is_refused(auth_client, key_route, body):
    kind, url = key_route
    _refused(auth_client.post(url, json=_body(kind, **body)), 'password')


def test_a_query_password_on_a_get_of_the_bulk_exports_is_refused(auth_client, material, app):
    for url in ('/api/v2/certificates/export', '/api/v2/cas/export'):
        _refused(auth_client.get(f'{url}?format=pem&password={SECRET}'), 'password')


@pytest.mark.parametrize('query', [
    'Password=%s', 'passphrase=%s', 'pass%%77ord=%s', 'x_PassWord_y=%s', 'password%%5B%%5D=%s',
])
def test_a_password_name_in_the_query_of_a_get_is_refused(auth_client, get_route, query):
    _kind, url = get_route
    _refused(auth_client.get(f'{url}?{query % SECRET}'), 'password')


@pytest.mark.parametrize('query', ['password=%s', 'Password=%s', 'passphrase=%s'])
def test_a_password_name_in_the_query_of_a_post_is_refused(auth_client, route, query):
    kind, url = route
    _refused(auth_client.post(f'{url}?{query % SECRET}', json=_body(kind)), 'password')


def test_the_query_password_refusal_of_a_get_is_kept(auth_client, key_route):
    kind, url = key_route
    if kind == 'key_recovery':
        pytest.skip('POST only')
    r = auth_client.get(f'{url}?password={SECRET}')
    _refused(r)


def test_a_refusal_never_cites_a_name_from_the_request(auth_client, key_route):
    kind, url = key_route
    name = 'Password' + 'n\x1b[31m' * 30 + 'TAIL'
    r = auth_client.post(url, json=_body(kind, **{name: SECRET}))
    _refused(r)
    assert 'TAIL' not in r.get_json()['message'] and '\x1b' not in r.get_json()['message']


# 5. What stays as it was

def test_unrelated_unknown_names_are_tolerated(auth_client, key_route):
    kind, url = key_route
    r = auth_client.post(f'{url}?trace=1', json=_body(kind, password=PASSWORD, note='x', n=3))
    assert r.status_code == 200, r.data[:300]


def test_a_get_without_a_body_is_unchanged(auth_client, get_route):
    kind, url = get_route
    q = '?format=pem' if kind not in ('csr',) else ''
    r = auth_client.get(f'{url}{q}&trace=1' if q else f'{url}?trace=1')
    assert r.status_code == 200, r.data[:300]
    if kind != 'user_certificate':  # its include_key defaults to true
        assert b'PRIVATE KEY' not in r.data


def test_a_json_post_still_exports_the_protected_key(auth_client, key_route):
    kind, url = key_route
    r = auth_client.post(url, json=_protected(kind))
    assert r.status_code == 200, r.data[:300]
    if PROTECTED_FORMAT[kind] in (None, 'pkcs12'):
        assert r.mimetype == 'application/x-pkcs12'
    else:
        assert b'ENCRYPTED PRIVATE KEY' in r.data


@pytest.mark.parametrize('empty', [None, ''])
@pytest.mark.parametrize('kind', ['certificate', 'ca', 'csr'])
def test_a_null_or_empty_password_still_means_a_key_in_clear(auth_client, material, app, kind, empty):
    url = _url(kind, material, app, auth_client)
    r = auth_client.post(url, json={'format': 'key', 'password': empty})
    assert r.status_code == 200, r.data[:300]
    assert b'PRIVATE KEY' in r.data and b'ENCRYPTED PRIVATE KEY' not in r.data


def test_the_csr_key_is_still_a_get_without_a_password(auth_client, material, app):
    url = _url('csr', material, app, auth_client)
    r = auth_client.get(f'{url}?format=key')
    assert r.status_code == 200 and b'PRIVATE KEY' in r.data


def test_a_post_without_a_body_is_unchanged(auth_client, material, app):
    r = auth_client.post(_url('certificate', material, app, auth_client))
    assert r.status_code == 200 and b'BEGIN CERTIFICATE' in r.data and b'PRIVATE KEY' not in r.data


def test_the_shapes_the_interface_sends_are_unchanged(auth_client, material, app):
    """Replays services/*.js: certificates, CAs and user certificates POST JSON, the CSR key GETs."""
    def call(url, **body):
        return auth_client.post(url, json=body)

    m = material
    for r in (
        call(f"/api/v2/certificates/{m['cert']}/export", format='pem', include_key=False,
             include_chain=True, include_root=False, legacy=False),
        call(f"/api/v2/certificates/{m['cert']}/export", format='pkcs12', include_key=False,
             include_chain=False, include_root=False, password=PASSWORD, legacy=False,
             chain_variant='auto'),
        call(f"/api/v2/cas/{m['ca']}/export", format='pem', include_key=False, include_chain=False,
             legacy=False),
        call(f"/api/v2/cas/{m['ca']}/export", format='pkcs12', include_key=True, include_chain=False,
             password=PASSWORD, legacy=False),
        call(f"/api/v2/user-certificates/{m['enrolment']}/export", format='pkcs12', include_key=True,
             include_chain=True, include_root=False, password=PASSWORD, legacy=False),
        call('/api/v2/certificates/export', format='pem', include_chain=False),
        call('/api/v2/cas/export', format='pem', include_chain=False),
        call(f"/api/v2/csrs/{m['csr']}/export", format='key', password=PASSWORD),
        call(f"/api/v2/mtls/certificates/{m['enrolment']}/download", format='pkcs12', password=PASSWORD,
             include_chain=True, include_root=False, legacy=False),
        auth_client.get(f"/api/v2/mtls/certificates/{m['enrolment']}/download"
                        '?format=pem&include_chain=true&include_root=false'),
        auth_client.get(f"/api/v2/csrs/{m['csr']}/export"),
    ):
        assert r.status_code == 200, (r.request.path, r.data[:200])


def test_a_permission_refusal_keeps_its_code(app, material, create_user):
    create_user(username='shape_viewer', role='viewer')
    client = app.test_client()
    assert client.post('/api/v2/auth/login', json={
        'username': 'shape_viewer', 'password': 'TestPass123!'}).status_code == 200
    r = client.post(f"/api/v2/csrs/{material['csr']}/export", json={'format': 'key', 'password': PASSWORD})
    assert r.status_code == 403
    r = client.post(f"/api/v2/cas/{material['ca']}/export", json={'format': 'key', 'password': PASSWORD})
    assert r.status_code == 403


# 6. A password given with a PEM that carries the key encrypts that key

PEM_KEY_ROUTES = {
    'certificate': ({'format': 'pem', 'include_key': True}, 'certificate',
                    'Private key exported as PEM (password-protected)'),
    'ca': ({'format': 'pem', 'include_key': True}, 'ca',
           'Private key exported as PEM (password-protected)'),
    'user_certificate': ({'format': 'pem'}, None,
                         'Exported PEM with private key (password-protected) for user cert: export-shape'),
}


def _key_blocks(data, label):
    begin, end = f'-----BEGIN {label}-----'.encode(), f'-----END {label}-----'.encode()
    blocks = []
    for chunk in data.split(begin)[1:]:
        blocks.append(begin + chunk.split(end)[0] + end + b'\n')
    return blocks


def _last_audit(app, kind, material):
    from models import AuditLog
    with app.app_context():
        if kind == 'user_certificate':
            query = AuditLog.query.filter_by(action='user_certificate_exported',
                                             resource_id=str(material['enrolment']))
        else:
            rid = material['cert'] if kind == 'certificate' else material['ca']
            query = AuditLog.query.filter_by(action='private_key_exported',
                                             resource_type=PEM_KEY_ROUTES[kind][1], resource_id=str(rid))
        entry = query.order_by(AuditLog.id.desc()).first()
        return entry.details if entry else None


@pytest.mark.parametrize('kind', list(PEM_KEY_ROUTES))
def test_a_password_with_a_pem_export_encrypts_its_key(auth_client, material, app, kind):
    from cryptography.hazmat.primitives import serialization
    url = _url(kind, material, app, auth_client)
    body, _rtype, audit = PEM_KEY_ROUTES[kind]
    plain = auth_client.post(url, json=body)
    assert plain.status_code == 200, plain.data[:300]
    original = [serialization.load_pem_private_key(b, None)
                for label in ('PRIVATE KEY', 'RSA PRIVATE KEY', 'EC PRIVATE KEY')
                for b in _key_blocks(plain.data, label)]
    assert len(original) == 1

    r = auth_client.post(url, json={**body, 'password': PASSWORD})
    assert r.status_code == 200, r.data[:300]
    for label in ('PRIVATE KEY', 'RSA PRIVATE KEY', 'EC PRIVATE KEY'):
        assert not _key_blocks(r.data, label), f'{label} in clear'
    encrypted = _key_blocks(r.data, 'ENCRYPTED PRIVATE KEY')
    assert len(encrypted) == 1
    key = serialization.load_pem_private_key(encrypted[0], PASSWORD.encode())
    assert key.private_numbers() == original[0].private_numbers()
    assert b'BEGIN CERTIFICATE' in r.data
    assert _last_audit(app, kind, material) == audit


@pytest.mark.parametrize('empty', [None, ''])
@pytest.mark.parametrize('kind', list(PEM_KEY_ROUTES))
def test_a_pem_export_without_a_password_keeps_its_key_in_clear(auth_client, material, app, kind, empty):
    url = _url(kind, material, app, auth_client)
    body, _rtype, audit = PEM_KEY_ROUTES[kind]
    r = auth_client.post(url, json={**body, 'password': empty})
    assert r.status_code == 200, r.data[:300]
    assert b'PRIVATE KEY-----' in r.data and b'ENCRYPTED PRIVATE KEY' not in r.data
    assert _last_audit(app, kind, material) == audit.replace('password-protected', 'unencrypted')


@pytest.mark.parametrize('kind', list(PEM_KEY_ROUTES))
def test_a_pem_export_password_follows_the_export_password_rule(auth_client, material, app, kind):
    url = _url(kind, material, app, auth_client)
    r = auth_client.post(url, json={**PEM_KEY_ROUTES[kind][0], 'password': 'short'})
    assert r.status_code == 400, r.data[:300]
    assert b'PRIVATE KEY' not in r.data and 'between 8 and' in r.get_json()['message']
