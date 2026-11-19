"""The ACME history pages, filters and sorts in the query, so a page and its total agree."""
import uuid

import pytest

from models import db, Certificate

ISSUER_A = 'CN=Hist CA A,O=Alpha'
ISSUER_B = 'CN=Hist CA B,O=Beta'


@pytest.fixture
def history(app):
    tag = uuid.uuid4().hex[:8]
    ids = []
    with app.app_context():
        for i in range(7):
            cert = Certificate(
                refid=str(uuid.uuid4()), descr=f'hist-{tag}-{i}',
                subject_cn=f'hist-{tag}-{i}', source='acme_client' if i < 5 else 'letsencrypt',
                issuer=ISSUER_A if i < 4 else ISSUER_B, revoked=i in (0, 1, 5),
                serial_number=f'{tag}{i}')
            db.session.add(cert)
            db.session.flush()
            ids.append(cert.id)
        db.session.commit()
    yield tag
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


def _get(client, tag, query=''):
    r = client.get(f'/api/v2/acme/history?search=hist-{tag}&{query}')
    assert r.status_code == 200, r.data
    return r.get_json()


def _names(body):
    return [row['common_name'] for row in body['data']]


def test_the_search_and_total_cover_the_set(auth_client, history):
    body = _get(auth_client, history, 'per_page=3&page=3')
    assert body['meta']['total'] == 7
    assert len(body['data']) == 1


def test_the_status_filter_reaches_every_page(auth_client, history):
    body = _get(auth_client, history, 'status=revoked&per_page=2&page=2')
    assert body['meta']['total'] == 3
    assert len(body['data']) == 1 and all(r['revoked'] for r in body['data'])
    body = _get(auth_client, history, 'status=valid&per_page=2')
    assert body['meta']['total'] == 4


def test_the_ca_filter_uses_the_name_shown(auth_client, history):
    body = _get(auth_client, history, 'ca=Hist CA B&per_page=10')
    assert body['meta']['total'] == 3
    assert {r['issuer'] for r in body['data']} == {'Hist CA B'}


def test_the_ca_options_cover_every_page(auth_client, history):
    body = _get(auth_client, history, 'per_page=1')
    assert {'Hist CA A', 'Hist CA B'} <= set(body['meta']['cas'])


def test_source_and_status_combine(auth_client, history):
    body = _get(auth_client, history, 'source=letsencrypt&status=revoked')
    assert body['meta']['total'] == 1


def test_the_sort_covers_the_whole_set(auth_client, history):
    asc = _get(auth_client, history, 'sort_by=common_name&sort_order=asc&per_page=2')
    desc = _get(auth_client, history, 'sort_by=common_name&sort_order=desc&per_page=2')
    assert _names(asc) == [f'hist-{history}-0', f'hist-{history}-1']
    assert _names(desc) == [f'hist-{history}-6', f'hist-{history}-5']
