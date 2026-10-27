"""
CSR lists: server-side paging and search.

The CSR page used to fetch each list once with the API's default page size
(20) and treat that page as the whole list, so the history stopped at 20
signed requests. The page now pages through the API, which these tests pin:
every signed request is reachable page by page, the totals count them all,
and the search covers every page (and the signing CA's name in the history).
"""
import json
import uuid

import pytest

CSRS = '/api/v2/csrs'
SIGNED = 23  # more than the old hard ceiling of one 20-row page


def _json(response):
    return json.loads(response.data)


def _create_csr(client, cn):
    r = client.post(CSRS, data=json.dumps({'cn': cn, 'key_type': 'RSA 2048'}),
                    content_type='application/json')
    assert r.status_code in (200, 201), r.data
    return _json(r)['data']['id']


def _sign(client, csr_id, ca_id):
    r = client.post(f'{CSRS}/{csr_id}/sign',
                    data=json.dumps({'ca_id': ca_id, 'validity_days': 365}),
                    content_type='application/json')
    assert r.status_code == 200, r.data
    # A policy queueing the signing for approval would leave a pending row
    assert not (_json(r).get('data') or {}).get('approval_required'), r.data


def _history(client, **params):
    qs = '&'.join(f'{k}={v}' for k, v in params.items())
    r = client.get(f'{CSRS}/history?{qs}')
    assert r.status_code == 200, r.data
    return _json(r)


@pytest.fixture(scope='module')
def signed_batch(auth_client, create_ca):
    """SIGNED requests signed by a CA no other test uses."""
    tag = uuid.uuid4().hex[:8]
    ca = create_ca(cn=f'Paging CA {tag}')
    ca_id = ca.get('id', ca.get('ca_id'))
    ids = []
    for i in range(SIGNED):
        csr_id = _create_csr(auth_client, f'paging-{tag}-{i:02d}.example.com')
        _sign(auth_client, csr_id, ca_id)
        ids.append(csr_id)
    return {'tag': tag, 'ids': ids, 'ca_name': f'Paging CA {tag}'}


class TestHistoryPaging:

    def test_every_signed_request_reachable_page_by_page(self, auth_client, signed_batch):
        first = _history(auth_client, page=1, per_page=10)
        total = first['meta']['total']
        assert total >= SIGNED
        seen = []
        for page in range(1, first['meta']['pages'] + 1):
            seen += [row['id'] for row in _history(auth_client, page=page, per_page=10)['data']]
        # No row twice, none missing -- equal timestamps included
        assert len(seen) == len(set(seen)) == total
        assert set(signed_batch['ids']) <= set(seen)

    def test_default_page_still_bounded(self, auth_client, signed_batch):
        body = _history(auth_client)
        assert len(body['data']) <= 20
        assert body['meta']['total'] >= SIGNED

    def test_search_reaches_rows_beyond_first_page(self, auth_client, signed_batch):
        # The oldest of the batch sits past the first page of 20
        oldest_cn = f"paging-{signed_batch['tag']}-00"
        body = _history(auth_client, search=oldest_cn, per_page=25)
        assert [row['id'] for row in body['data']] == [signed_batch['ids'][0]]
        assert body['meta']['total'] == 1

    def test_search_matches_signing_ca_name(self, auth_client, signed_batch):
        body = _history(auth_client, search=signed_batch['ca_name'].replace(' ', '%20'),
                        per_page=100)
        assert body['meta']['total'] == SIGNED
        assert {row['id'] for row in body['data']} == set(signed_batch['ids'])

    def test_like_wildcards_are_literal(self, auth_client, signed_batch):
        # Unescaped, '%' and '_' would match this batch's names ('<tag>-00...')
        tag = signed_batch['tag']
        assert _history(auth_client, search=f'{tag}%25')['meta']['total'] == 0
        assert _history(auth_client, search=f'{tag}___')['meta']['total'] == 0
        assert _history(auth_client, search=f'{tag}-0_')['meta']['total'] == 0

    def test_sort_by_common_name_across_pages(self, auth_client, signed_batch):
        tag = signed_batch['tag']
        seen = []
        for page in (1, 2, 3):
            body = _history(auth_client, search=f'paging-{tag}', sort_by='cn',
                            sort_order='asc', page=page, per_page=10)
            seen += [row['id'] for row in body['data']]
        # Names are numbered in signing order: ascending CN is signing order
        assert seen == signed_batch['ids']
        body = _history(auth_client, search=f'paging-{tag}', sort_by='cn',
                        sort_order='desc', per_page=100)
        assert [row['id'] for row in body['data']] == signed_batch['ids'][::-1]

    def test_unknown_sort_key_falls_back(self, auth_client, signed_batch):
        tag = signed_batch['tag']
        body = _history(auth_client, search=f'paging-{tag}', sort_by='prv',
                        sort_order='asc', per_page=100)
        assert {row['id'] for row in body['data']} == set(signed_batch['ids'])

    def test_overlong_search_is_accepted_and_bounded(self, auth_client, signed_batch):
        body = _history(auth_client, search='x' * 5000)
        assert body['meta']['total'] == 0


class TestPendingSearch:

    def test_pending_search_unchanged(self, auth_client):
        tag = uuid.uuid4().hex[:8]
        csr_id = _create_csr(auth_client, f'pending-{tag}.example.com')
        r = auth_client.get(f'{CSRS}?search=pending-{tag}')
        assert r.status_code == 200
        body = _json(r)
        assert [row['id'] for row in body['data']] == [csr_id]
        assert body['meta']['total'] == 1
        # The signer clause is history-only: pending rows have no signer yet
        r = auth_client.get(f'{CSRS}?search=pending-{tag}%25')
        assert _json(r)['meta']['total'] == 0
