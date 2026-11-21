"""(b) Twenty issuances in parallel over both nodes: distinct serials, a count of twenty."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.ha.cluster import create_ca, issue

pytestmark = pytest.mark.ha

COUNT = 20


def test_parallel_issuance_on_both_nodes(cluster, admin):
    clients = [admin, admin.on(cluster[1])]
    ca = create_ca(admin, 'HA issuance CA')

    with ThreadPoolExecutor(max_workers=COUNT) as pool:
        certs = list(pool.map(lambda i: issue(clients[i % 2], ca['id'], f'ha-{i}.example.test'),
                              range(COUNT)))

    serials = [c['serial_number'] for c in certs]
    assert len(set(serials)) == COUNT, serials
    r = clients[1].get(f"/api/v2/cas/{ca['id']}")
    assert r.status_code == 200 and r.json()['data']['serial'] == COUNT, (
        cluster.sql('SELECT id, serial FROM certificate_authorities'), r.json()['data'].get('serial'))
    rows = cluster.sql('SELECT serial_number FROM certificates WHERE caref = %s', (ca['refid'],))
    assert sorted(s for (s,) in rows) == sorted(serials)

    # The database itself refuses a second certificate with one of these serials under this CA
    import psycopg
    with pytest.raises(psycopg.errors.UniqueViolation):
        cluster.sql('INSERT INTO certificates (refid, descr, crt, caref, serial_number) '
                    'SELECT %s, descr, crt, caref, serial_number FROM certificates WHERE id = %s',
                    ('ha-duplicate-serial', certs[0]['id']))
