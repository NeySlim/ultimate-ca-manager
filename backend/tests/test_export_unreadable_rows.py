"""Every route that exports several certificates or CAs skips unreadable rows, names them, and
answers the same in PEM and P7B when none is readable."""
import base64
import datetime
import json

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
    made = {'cert': [create_cert(cn=f'unreadable-{i}.example.com')['id'] for i in range(2)],
            'ca': [create_ca(cn=f'Unreadable CA {i}')['id'] for i in range(2)]}
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

    def corrupt(route, row_id):
        with app.app_context():
            row = db.session.get(_model(route), row_id)
            col = _column(route)
            saved.append((route, row_id, getattr(row, col)))
            setattr(row, col, 'garbage' if route.kind == 'trust' else GARBAGE)
            db.session.commit()

    def corrupt_all(route):
        with app.app_context():
            ids = [r.id for r in _model(route).query.all()]
        for i in ids:
            corrupt(route, i)

    yield made, corrupt, corrupt_all
    with app.app_context():
        for route, row_id, value in saved:
            setattr(db.session.get(_model(route), row_id), _column(route), value)
        for model, key in ((TrustedCertificate, 'trust'), (Certificate, 'cert'), (CA, 'ca')):
            model.query.filter(model.id.in_(made[key])).delete(synchronize_session=False)
        db.session.commit()


@EVERY
@BOTH
def test_an_unreadable_row_is_skipped_logged_and_named(auth_client, rows, route, fmt, caplog):
    made, corrupt, _ = rows
    ids = made[route.kind]
    corrupt(route, ids[0])
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
    made, _, corrupt_all = rows
    corrupt_all(route)
    answers = [route.call(auth_client, made[route.kind], fmt) for fmt in ('pem', 'p7b')]
    assert answers[0].status_code == answers[1].status_code == 404
    for r in answers:
        details = r.get_json()['details']
        assert set(str(i) for i in made[route.kind]) <= set(details['skipped'])
        assert details['skipped_count'] >= 2
        assert 'No readable' in r.get_json()['detail']
    assert answers[0].get_json() == answers[1].get_json()


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
