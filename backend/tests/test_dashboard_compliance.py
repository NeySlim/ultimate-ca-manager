"""GET /api/v2/dashboard/compliance: counters over the live issued certificates,
read from columns; the request never parses a certificate."""
import uuid
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from models import Certificate, db
from models.certificate_template import CertificateTemplate
from tests.conftest import get_json
from tests.dashboard_pem import self_signed, sha1_rsa
from utils.datetime_utils import utc_now

URL = '/api/v2/dashboard/compliance'
COUNTERS = ('rsa_below_3072', 'weak_signature_hash', 'server_lifetime_over_398_days',
            'incomplete_chain', 'no_private_key')


def _rsa(bits):
    return self_signed(rsa.generate_private_key(public_exponent=65537, key_size=bits))


@pytest.fixture(scope='module')
def pems():
    return {'rsa2048': _rsa(2048), 'rsa4096': _rsa(4096), 'sha1': sha1_rsa(),
            'ec': self_signed(ec.generate_private_key(ec.SECP256R1()))}


def _summary(client):
    r = client.get(URL)
    assert r.status_code == 200, r.data
    return get_json(r)['data']


def _counts(data):
    return {name: data['counters'][name]['count'] for name in COUNTERS}


def _algos(data):
    return {a['key_algo']: a['count'] for a in data['by_key_algorithm']}


@pytest.fixture
def rows(app):
    created = []

    def add(pem, lifetime_days=90, **kw):
        now = utc_now()
        kw.setdefault('prv', 'key')
        row = Certificate(refid=str(uuid.uuid4()), descr='compliance-test', crt=pem,
                          valid_from=now - timedelta(days=1),
                          valid_to=now - timedelta(days=1) + timedelta(days=lifetime_days), **kw)
        db.session.add(row)
        db.session.flush()
        created.append(row.id)
        return row
    yield add
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(created)).delete(synchronize_session=False)
        db.session.commit()


def test_counters_are_exact(app, auth_client, pems, rows):
    before = _summary(auth_client)
    with app.app_context():
        template = CertificateTemplate(name=f'compliance-web-{uuid.uuid4()}', template_type='web_server',
                                       extensions_template='{}')
        db.session.add(template)
        db.session.flush()
        template_id = template.id
        rows(pems['rsa2048'])
        rows(pems['rsa4096'])
        rows(pems['ec'], prv=None)
        rows(pems['sha1'])
        rows(pems['rsa4096'], lifetime_days=400, cert_type='server_cert')
        rows(pems['ec'], lifetime_days=400, template_id=template_id)
        rows(pems['ec'], lifetime_days=398, cert_type='server_cert')  # 398 days is still short
        rows(pems['rsa4096'], lifetime_days=400, cert_type='client_cert')
        # Neither revoked, archived nor expired certificates count
        rows(pems['sha1'], revoked=True, prv=None, cert_type='server_cert', lifetime_days=900)
        rows(pems['rsa2048'], archived=True, prv=None)
        rows(pems['rsa2048'], lifetime_days=-5, prv=None)
        db.session.commit()
    try:
        after = _summary(auth_client)
        assert after['total'] - before['total'] == 8
        delta = {k: _counts(after)[k] - _counts(before)[k] for k in COUNTERS}
        assert delta == {'rsa_below_3072': 2, 'weak_signature_hash': 1, 'server_lifetime_over_398_days': 2,
                         'incomplete_chain': 0, 'no_private_key': 1}
        algos_before, algos_after = _algos(before), _algos(after)
        assert {k: algos_after.get(k, 0) - algos_before.get(k, 0) for k in algos_after
                if algos_after.get(k, 0) != algos_before.get(k, 0)} == {
            'RSA 2048': 2, 'RSA 4096': 3, 'EC secp256r1': 3}
    finally:
        with app.app_context():
            Certificate.query.filter(Certificate.template_id == template_id).update(
                {Certificate.template_id: None}, synchronize_session=False)
            db.session.delete(db.session.get(CertificateTemplate, template_id))
            db.session.commit()


@pytest.mark.sqlite_only(reason='an orphan caref is refused by the foreign key')
def test_an_orphan_counts_as_an_incomplete_chain(app, auth_client, pems, rows):
    before = _counts(_summary(auth_client))['incomplete_chain']
    with app.app_context():
        rows(pems['ec'], caref=f'missing-ca-{uuid.uuid4()}')
        db.session.commit()
    assert _counts(_summary(auth_client))['incomplete_chain'] == before + 1


def test_the_request_parses_no_certificate(app, auth_client, pems, rows, monkeypatch):
    with app.app_context():
        for name in pems:
            rows(pems[name])
        db.session.commit()
    calls = []
    for loader in ('load_pem_x509_certificate', 'load_der_x509_certificate'):
        original = getattr(x509, loader)
        monkeypatch.setattr(x509, loader, lambda *a, _o=original, **k: calls.append(1) or _o(*a, **k))
    _summary(auth_client)
    assert calls == []


def _entries(data):
    return [(name, c) for name, c in data['counters'].items()] + [
        (f"key_algo:{a['key_algo']}", a) for a in data['by_key_algorithm']]


# No counter has a list filter that reproduces it today: the list keeps archived
# rows under every status and has no key, hash, lifetime or missing-key filter
FILTERABLE = set()


def test_a_counter_without_a_list_filter_says_so(app, auth_client, pems, rows):
    with app.app_context():
        rows(pems['rsa2048'])
        rows(pems['ec'], prv=None)
        db.session.commit()
    data = _summary(auth_client)
    assert data['by_key_algorithm']
    for name, entry in _entries(data):
        assert entry['filter_available'] is (name in FILTERABLE), name
        if not entry['filter_available']:
            assert entry['filter_hint'] is None, name


def test_every_hint_given_lists_exactly_what_it_counts(app, auth_client, pems, rows):
    """An emitted hint, passed to the certificate list as is, gives back the counter."""
    with app.app_context():
        rows(pems['rsa2048'])
        rows(pems['ec'], prv=None)
        rows(pems['rsa2048'], archived=True)
        db.session.commit()
    data = _summary(auth_client)
    hinted = [(name, e) for name, e in _entries(data) if e['filter_available']]
    assert {name for name, _ in hinted} == FILTERABLE
    for name, entry in hinted:
        r = auth_client.get('/api/v2/certificates', query_string={**entry['filter_hint'], 'per_page': 1})
        assert r.status_code == 200, (name, r.data)
        assert get_json(r)['meta']['total'] == entry['count'], name


def test_requires_auth(client):
    assert client.get(URL).status_code == 401
