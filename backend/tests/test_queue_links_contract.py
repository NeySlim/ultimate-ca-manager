"""The work queue's links and the pages that read them stay one table.

`contracts/queue_links.json` is the table; the server's `_HREF` must equal it, and
`frontend/src/pages/__tests__/queueLinks.contract.test.jsx` holds the pages to the other half.
"""
import json
import os

from services import dashboard_aggregates as agg

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
with open(os.path.join(_REPO, 'contracts', 'queue_links.json')) as _fh:
    LINKS = json.load(_fh)['links']


def test_contract_covers_every_kind_once():
    kinds = [row['kind'] for row in LINKS]
    assert sorted(kinds) == sorted(agg.QUEUE_KINDS)


def test_server_templates_are_the_contract_templates():
    assert {row['kind']: row['template'] for row in LINKS} == agg._HREF


def test_contract_names_what_the_template_carries():
    for row in LINKS:
        query = row['template'].partition('?')[2]
        pairs = dict(p.split('=') for p in query.split('&') if p)
        assert pairs.get('tab') == row['tab'], row['kind']
        if row['param']:
            assert pairs.get(row['param']) == '{id}', row['kind']
