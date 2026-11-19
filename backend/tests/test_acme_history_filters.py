"""The ACME history pages, filters and sorts in the query, so a page and its total agree."""
import uuid
from datetime import datetime

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


@pytest.fixture
def mixed(app):
    """Sources interleaved in creation order, so no other column sort can mimic a source sort."""
    tag = uuid.uuid4().hex[:8]
    ids = []
    with app.app_context():
        for i, src in enumerate(['letsencrypt', 'acme_client', 'letsencrypt', 'acme_client']):
            cert = Certificate(refid=str(uuid.uuid4()), descr=f'mix-{tag}-{i}', subject_cn=f'mix-{tag}-{i}',
                               source=src, serial_number=f'{tag}{i}')
            db.session.add(cert)
            db.session.flush()
            ids.append(cert.id)
        db.session.commit()
    yield tag
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


@pytest.mark.parametrize('order', ['asc', 'desc'])
def test_the_source_column_sorts_the_whole_set(auth_client, mixed, order):
    r = auth_client.get(f'/api/v2/acme/history?search=mix-{mixed}&sort_by=source&sort_order={order}')
    got = [row['source'] for row in r.get_json()['data']]
    assert got == (['acme_client'] * 2 + ['letsencrypt'] * 2 if order == 'asc'
                   else ['letsencrypt'] * 2 + ['acme_client'] * 2)


@pytest.fixture
def gaps(app):
    """Rows with a name or an expiry and rows with neither (descr carries the search tag)."""
    tag = uuid.uuid4().hex[:8]
    ids = []
    with app.app_context():
        for i, (cn, until) in enumerate([('gap-b', datetime(2030, 1, 1)), ('gap-a', datetime(2031, 1, 1)),
                                         (None, None)]):
            cert = Certificate(
                refid=str(uuid.uuid4()), descr=f'gap-{tag}-{i}', subject_cn=cn, valid_to=until,
                source='acme_client', serial_number=f'{tag}{i}')
            db.session.add(cert)
            db.session.flush()
            ids.append(cert.id)
        db.session.commit()
    yield tag
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


@pytest.mark.parametrize('column', ['common_name', 'valid_to'])
@pytest.mark.parametrize('order', ['asc', 'desc'])
def test_absent_values_come_last_in_both_directions(auth_client, gaps, column, order):
    r = auth_client.get(f'/api/v2/acme/history?search=gap-{gaps}&sort_by={column}&sort_order={order}')
    rows = r.get_json()['data']
    assert len(rows) == 3
    assert rows[-1]['valid_to'] is None, rows
