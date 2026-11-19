"""The user certificate list filters and sorts in the query, so pages and total agree."""
from datetime import datetime

import pytest

from models import Certificate, User, db
from models.auth_certificate import AuthCertificate

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

URL = '/api/v2/user-certificates'


@pytest.fixture
def enrolments(app, create_cert):
    """Five enrolments named ucl-0 (oldest) to ucl-4; ucl-0, 1 and 2 are revoked."""
    made = []
    with app.app_context():
        admin_id = User.query.filter_by(username='admin').first().id
    for i in range(5):
        cert = create_cert(cn=f'ucl-{i}.example')
        with app.app_context():
            issued = db.session.get(Certificate, cert['id'])
            issued.revoked = i < 3
            row = AuthCertificate(
                user_id=admin_id, cert_serial=issued.serial_number,
                cert_subject=issued.subject or f'CN=ucl-{i}.example',
                cert_issuer=issued.issuer, cert_fingerprint='',
                name=f'ucl-{i}', enabled=True)
            db.session.add(row)
            db.session.commit()
            made.append(row.id)
    yield made
    with app.app_context():
        AuthCertificate.query.filter(AuthCertificate.id.in_(made)).delete(
            synchronize_session=False)
        db.session.commit()


def _get(client, query):
    r = client.get(f'{URL}?search=ucl-&{query}')
    assert r.status_code == 200, r.data
    return r.get_json()['data']


def test_the_status_filter_reaches_rows_beyond_the_first_page(auth_client, enrolments):
    first = _get(auth_client, 'status=revoked&per_page=2&page=1')
    second = _get(auth_client, 'status=revoked&per_page=2&page=2')
    assert first['total'] == 3 and first['pages'] == 2
    assert [i['name'] for i in first['items']] == ['ucl-2', 'ucl-1']
    assert [i['name'] for i in second['items']] == ['ucl-0']
    assert all(i['status'] == 'revoked' for i in first['items'] + second['items'])


def test_the_total_is_the_filtered_count(auth_client, enrolments):
    valid = _get(auth_client, 'status=valid&per_page=1')
    assert valid['total'] == 2 and valid['pages'] == 2
    assert _get(auth_client, 'per_page=1')['total'] == 5


def test_two_statuses_are_paged_together(auth_client, enrolments):
    both = _get(auth_client, 'status=revoked&status=valid&per_page=4')
    assert both['total'] == 5 and len(both['items']) == 4


def test_the_sort_covers_the_whole_set(auth_client, enrolments):
    first = _get(auth_client, 'sort_by=name&sort_order=asc&per_page=2&page=1')
    last = _get(auth_client, 'sort_by=name&sort_order=desc&per_page=2&page=1')
    assert [i['name'] for i in first['items']] == ['ucl-0', 'ucl-1']
    assert [i['name'] for i in last['items']] == ['ucl-4', 'ucl-3']


@pytest.fixture
def odd_rows(app):
    """One enrolment named with an underscore, one with no name and no expiry."""
    with app.app_context():
        admin_id = User.query.filter_by(username='admin').first().id
        rows = [
            AuthCertificate(user_id=admin_id, cert_serial='9001', cert_subject='CN=odd-1',
                            name='odd_name', valid_until=datetime(2030, 1, 1), enabled=True),
            AuthCertificate(user_id=admin_id, cert_serial='9002', cert_subject='CN=odd-2',
                            name=None, valid_until=None, enabled=True),
            AuthCertificate(user_id=admin_id, cert_serial='9003', cert_subject='CN=odd-3',
                            name='odd-z', valid_until=datetime(2031, 1, 1), enabled=True),
        ]
        db.session.add_all(rows)
        db.session.commit()
        ids = [r.id for r in rows]
    yield ids
    with app.app_context():
        AuthCertificate.query.filter(AuthCertificate.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


def test_an_underscore_in_the_search_is_literal(auth_client, odd_rows):
    got = auth_client.get(f'{URL}?search=odd_name').get_json()['data']
    assert [i['name'] for i in got['items']] == ['odd_name']
    assert auth_client.get(f'{URL}?search=odd%25').get_json()['data']['total'] == 0


@pytest.mark.parametrize('column', ['name', 'valid_until'])
@pytest.mark.parametrize('order', ['asc', 'desc'])
def test_absent_values_come_last_in_both_directions(auth_client, odd_rows, column, order):
    got = auth_client.get(
        f'{URL}?search=odd-&sort_by={column}&sort_order={order}').get_json()['data']
    names = [i['name'] for i in got['items']]
    assert len(names) == 3 and names[-1] is None, names
