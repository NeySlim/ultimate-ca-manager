"""(c) Revocations on both nodes, then CRLs from both: increasing crlNumber, every revocation listed."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography import x509

from tests.ha.cluster import create_ca, issue

pytestmark = pytest.mark.ha

CERTS = 10
ROUNDS = 3


def _crl_number(pem):
    crl = x509.load_pem_x509_crl(pem.encode())
    return crl, crl.extensions.get_extension_for_class(x509.CRLNumber).value.crl_number


def test_revocations_on_both_nodes_then_crl(cluster, admin):
    clients = [admin, admin.on(cluster[1])]
    ca = create_ca(admin, 'HA CRL CA')
    certs = [issue(clients[i % 2], ca['id'], f'crl-{i}.example.test') for i in range(CERTS)]

    def revoke(i):
        r = clients[i % 2].post(f"/api/v2/certificates/{certs[i]['id']}/revoke", {'reason': 'superseded'})
        assert r.status_code == 200, f'revoke on {clients[i % 2].node.name}: {r.status_code} {r.text[:500]}'

    with ThreadPoolExecutor(max_workers=CERTS) as pool:
        list(pool.map(revoke, range(CERTS)))

    def regenerate(client):
        r = client.post(f"/api/v2/crl/{ca['id']}/regenerate")
        assert r.status_code == 200, f'CRL on {client.node.name}: {r.status_code} {r.text[:500]}'
        return r.json()['data']['crl_number']

    rounds = []
    for _ in range(ROUNDS):
        with ThreadPoolExecutor(max_workers=4) as pool:
            rounds.append(sorted(pool.map(regenerate, clients * 2)))
    numbers = [n for numbers in rounds for n in numbers]
    assert len(set(numbers)) == len(numbers), rounds
    # A CRL generated after another one finished carries a higher number
    assert all(max(earlier) < min(later) for earlier, later in zip(rounds, rounds[1:])), rounds

    r = clients[1].get(f"/api/v2/crl/{ca['id']}")
    assert r.status_code == 200
    crl, number = _crl_number(r.json()['data']['crl_pem'])
    assert number == max(numbers)
    listed = {entry.serial_number for entry in crl}
    # The API returns the stored spelling of a serial: one decimal string
    assert {int(c['serial_number']) for c in certs} <= listed

    stored = [n for (n,) in cluster.sql('SELECT crl_number FROM crl_metadata WHERE ca_id = %s', (ca['id'],))]
    assert len(set(stored)) == len(stored) and max(stored) == number, stored
