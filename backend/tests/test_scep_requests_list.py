"""The SCEP request list pages, filters by status and searches on the server."""
import uuid

import pytest

from models import db
from models.scep import SCEPRequest


@pytest.fixture
def requests_rows(app):
    tag = uuid.uuid4().hex[:8]
    ids = []
    with app.app_context():
        for i in range(60):
            row = SCEPRequest(
                transaction_id=f'tx-{tag}-{i:02d}', csr='AAAA',
                status='approved' if i % 3 == 0 else 'pending',
                subject=f'CN=dev-{tag}-{i:02d}')
            db.session.add(row)
            db.session.flush()
            ids.append(row.id)
        db.session.commit()
    yield tag
    with app.app_context():
        SCEPRequest.query.filter(SCEPRequest.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


def _get(client, query):
    r = client.get(f'/api/v2/scep/requests?{query}')
    assert r.status_code == 200, r.data
    return r.get_json()


def test_requests_beyond_the_first_fifty_are_reachable(auth_client, requests_rows):
    body = _get(auth_client, f'search={requests_rows}&per_page=50&page=2')
    assert body['meta']['total'] == 60
    assert len(body['data']) == 10


def test_the_status_filter_pages_with_its_own_total(auth_client, requests_rows):
    body = _get(auth_client, f'search={requests_rows}&status=approved&per_page=8&page=3')
    assert body['meta']['total'] == 20 and body['meta']['total_pages'] == 3
    assert len(body['data']) == 4 and all(r['status'] == 'approved' for r in body['data'])


def test_the_search_reads_subject_and_transaction(auth_client, requests_rows):
    body = _get(auth_client, f'search=dev-{requests_rows}-07')
    assert [r['subject'] for r in body['data']] == [f'CN=dev-{requests_rows}-07']
    assert _get(auth_client, f'search=tx-{requests_rows}-08')['meta']['total'] == 1


def test_the_default_page_is_still_fifty(auth_client, requests_rows):
    body = _get(auth_client, f'search={requests_rows}')
    assert len(body['data']) == 50 and body['meta']['per_page'] == 50


def test_several_statuses_are_kept(auth_client, requests_rows):
    body = _get(auth_client, f'search={requests_rows}&status=approved&status=pending&per_page=10')
    assert body['meta']['total'] == 60


def test_an_unknown_status_is_refused_like_the_user_certificates(auth_client, requests_rows):
    r = auth_client.get(f'/api/v2/scep/requests?search={requests_rows}&status=bogus')
    assert r.status_code == 400
    assert 'bogus' in r.get_json()['message']
