"""Every route that exports several certificates or CAs skips unreadable rows, names them, and
answers the same in PEM and P7B when none is readable."""
import base64
import datetime
import json
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from models import db, Certificate, CA
from models.truststore import TrustedCertificate
from utils.export_pems import readable_pems, skipped_headers, SKIPPED_LIST_LIMIT

GARBAGE = base64.b64encode(b'not a certificate').decode()


def _pem(cn):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM)


class Route:
    def __init__(self, name, kind, header, call):
        self.name, self.kind, self.header, self.call = name, kind, header, call

    def __repr__(self):
        return self.name


def _certs_all(c, ids, fmt):
    return c.get(f'/api/v2/certificates/export?format={fmt}')


def _certs_bulk(c, ids, fmt):
    return c.post('/api/v2/certificates/bulk/export', data=json.dumps({'ids': ids, 'format': fmt}),
                  content_type='application/json')


def _cas_all(c, ids, fmt):
    return c.get(f'/api/v2/cas/export?format={fmt}')


def _cas_bulk(c, ids, fmt):
    return c.post('/api/v2/cas/bulk/export', data=json.dumps({'ids': ids, 'format': fmt}),
                  content_type='application/json')


def _trust(c, ids, fmt):
    return c.get(f'/api/v2/truststore/export?format={fmt}')


ROUTES = [
    Route('certificates/export', 'cert', 'Certificates', _certs_all),
    Route('certificates/bulk/export', 'cert', 'Certificates', _certs_bulk),
    Route('cas/export', 'ca', 'CAs', _cas_all),
    Route('cas/bulk/export', 'ca', 'CAs', _cas_bulk),
    Route('truststore/export', 'trust', 'Certificates', _trust),
]
BOTH = pytest.mark.parametrize('fmt', ['pem', 'p7b'])
EVERY = pytest.mark.parametrize('route', ROUTES, ids=repr)


def _model(route):
    return {'cert': Certificate, 'ca': CA, 'trust': TrustedCertificate}[route.kind]


def _column(route):
    return 'certificate_pem' if route.kind == 'trust' else 'crt'


def _count(route, fmt, data):
    if fmt == 'p7b':
        return len(pkcs7.load_der_pkcs7_certificates(data))
    return data.count(b'-----BEGIN CERTIFICATE-----')


@pytest.fixture
def rows(app, create_cert, create_ca):
    """Two readable rows per kind, plus a restore of every row touched."""
    saved = []
    # the certificates are issued by a CA of this file, removed with it
    made = {'ca': [create_ca(cn=f'Unreadable CA {i}')['id'] for i in range(2)]}
    made['cert'] = [create_cert(cn=f'unreadable-{i}.example.com', ca_id=made['ca'][0])['id'] for i in range(2)]
    with app.app_context():
        trust = []
        for i in range(2):
            pem = _pem(f'trust-{i}')
            row = TrustedCertificate(name=f'trust-{i}', certificate_pem=pem.decode(),
                                     fingerprint_sha256=f'{i:064x}', purpose='root_ca')
            db.session.add(row)
            db.session.flush()
            trust.append(row.id)
        db.session.commit()
        made['trust'] = trust

    def store(route, row_id, value):
        with app.app_context():
            row = db.session.get(_model(route), row_id)
            col = _column(route)
            saved.append((route, row_id, getattr(row, col)))
            setattr(row, col, value)
            db.session.commit()

    def corrupt(route, row_id):
        store(route, row_id, 'garbage' if route.kind == 'trust' else GARBAGE)

    def corrupt_all(route):
        """Corrupts every row the route selects and returns how many."""
        with app.app_context():
            ids = [r.id for r in _model(route).query.all()
                   if route.kind == 'trust' or getattr(r, _column(route))]
        for i in ids:
            corrupt(route, i)
        return len(ids)

    yield SimpleNamespace(made=made, store=store, corrupt=corrupt, corrupt_all=corrupt_all)
    with app.app_context():
        for route, row_id, value in reversed(saved):
            setattr(db.session.get(_model(route), row_id), _column(route), value)
        for model, key in ((TrustedCertificate, 'trust'), (Certificate, 'cert'), (CA, 'ca')):
            model.query.filter(model.id.in_(made[key])).delete(synchronize_session=False)
        db.session.commit()


@EVERY
@BOTH
def test_an_unreadable_row_is_skipped_logged_and_named(auth_client, rows, route, fmt, caplog):
    ids = rows.made[route.kind]
    rows.corrupt(route, ids[0])
    with caplog.at_level('WARNING'):
        r = route.call(auth_client, ids, fmt)
    assert r.status_code == 200, r.data
    named = r.headers[f'X-Skipped-{route.header}'].split(',')
    assert str(ids[0]) in named and str(ids[1]) not in named
    assert r.headers[f'X-Skipped-{route.header}-Count'] == str(len(named))
    assert _count(route, fmt, r.data) >= 1
    assert any('skips' in m and str(ids[0]) in m for m in caplog.messages)


@EVERY
def test_no_readable_row_answers_the_same_in_both_formats(auth_client, rows, route):
    made = rows.made[route.kind]
    corrupted = rows.corrupt_all(route)
    # a bulk route reads the selection, the others the whole table, neighbours' rows included
    n = len(made) if 'bulk' in route.name else corrupted
    answers = [route.call(auth_client, made, fmt) for fmt in ('pem', 'p7b')]
    assert answers[0].status_code == answers[1].status_code == 404
    for r in answers:
        details = r.get_json()['details']
        assert details['skipped_count'] == n
        assert len(details['skipped']) == min(n, SKIPPED_LIST_LIMIT)
        if n <= SKIPPED_LIST_LIMIT:
            assert set(str(i) for i in made) <= set(details['skipped'])
        assert 'No readable' in r.get_json()['detail']
    assert answers[0].get_json() == answers[1].get_json()


def _forms():
    """Each shape of a valid stored certificate: (label, PEM bytes, certificates it holds)."""
    bare, first, second, crlf = (_pem(f'form-{n}') for n in ('bare', 'first', 'second', 'crlf'))
    pkcs12_text = b'Bag Attributes\n    localKeyID: 01 02\nsubject=CN=form-p12\nissuer=CN=form-p12\n'
    x509_text = b'Certificate:\n    Data:\n        Version: 3 (0x2)\n'
    p12, text = _pem('form-p12'), _pem('form-text')
    return [
        ('bare', bare, [bare]),
        ('after-pkcs12-attributes', pkcs12_text + p12, [p12]),
        ('after-x509-text', x509_text + text, [text]),
        ('two-certificates', first + second, [first, second]),
        ('crlf', crlf.replace(b'\n', b'\r\n'), [crlf]),
    ]


FORMS = _forms()


@EVERY
@BOTH
@pytest.mark.parametrize('form', FORMS, ids=lambda f: f[0])
def test_every_valid_stored_form_exports_as_before(auth_client, rows, route, fmt, form):
    """What the base exported from a valid row it still exports, the same bytes in PEM."""
    label, pem, certs = form
    row_id = rows.made[route.kind][0]
    stored = pem.decode() if route.kind == 'trust' else base64.b64encode(pem).decode()
    rows.store(route, row_id, stored)
    r = route.call(auth_client, rows.made[route.kind], fmt)
    assert r.status_code == 200, r.data
    assert str(row_id) not in r.headers.get(f'X-Skipped-{route.header}', '').split(',')
    if fmt == 'pem':
        if route.kind == 'trust':
            # the bundle names each entry, found through the stored PEM itself
            expected = f'# trust-0\n{pem.decode().strip()}\n'.encode()
        else:
            expected = pem if pem.endswith(b'\n') else pem + b'\n'
        assert expected in r.data
        return
    exported = [c.public_bytes(serialization.Encoding.DER) for c in pkcs7.load_der_pkcs7_certificates(r.data)]
    wanted = [x509.load_pem_x509_certificate(c).public_bytes(serialization.Encoding.DER) for c in certs]
    if route.kind == 'trust':
        # a trust store entry is the one certificate it was accepted for, its first
        assert wanted[0] in exported and not any(w in exported for w in wanted[1:])
    else:
        at = exported.index(wanted[0])
        assert exported[at:at + len(wanted)] == wanted


@BOTH
def test_a_trust_entry_is_read_by_its_first_certificate(auth_client, rows, fmt):
    """The store accepts an entry by its first certificate; a broken block after it does not hide it."""
    route = next(r for r in ROUTES if r.kind == 'trust')
    first = _pem('trust-first')
    stored = first + b'-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n'
    rows.store(route, rows.made['trust'][0], stored.decode())
    r = route.call(auth_client, rows.made['trust'], fmt)
    assert r.status_code == 200, r.data
    assert 'X-Skipped-Certificates' not in r.headers
    if fmt == 'pem':
        assert stored.strip() in r.data
    else:
        der = x509.load_pem_x509_certificate(first).public_bytes(serialization.Encoding.DER)
        assert der in [c.public_bytes(serialization.Encoding.DER) for c in pkcs7.load_der_pkcs7_certificates(r.data)]


def test_readable_pems_skips_null_and_empty_rows():
    good = base64.b64encode(_pem('good')).decode()
    pems, skipped = readable_pems([(1, None), (2, ''), (3, GARBAGE), (4, good)])
    assert len(pems) == 1 and skipped == ['1', '2', '3']


def test_the_skipped_header_is_bounded_and_counted():
    skipped = [str(i) for i in range(SKIPPED_LIST_LIMIT + 50)]
    headers = skipped_headers(skipped, 'CAs')
    assert len(headers['X-Skipped-CAs'].split(',')) == SKIPPED_LIST_LIMIT
    assert headers['X-Skipped-CAs-Count'] == str(SKIPPED_LIST_LIMIT + 50)
    assert skipped_headers([], 'CAs') == {}


def test_the_skipped_headers_are_exposed_to_a_cross_origin_screen(app, auth_client):
    from utils.public_endpoints import get_cors_origins
    with app.app_context():
        origin = get_cors_origins()[0]
    r = auth_client.get('/api/v2/certificates/export', headers={'Origin': origin})
    exposed = r.headers.get('Access-Control-Expose-Headers', '')
    for name in ('X-Skipped-Certificates', 'X-Skipped-Certificates-Count', 'X-Skipped-CAs', 'X-Skipped-CAs-Count'):
        assert name in exposed
