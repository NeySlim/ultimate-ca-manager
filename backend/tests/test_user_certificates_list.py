"""The user certificate list filters and sorts in the query, so pages and total agree."""
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
