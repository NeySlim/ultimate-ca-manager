"""A real rolling restart of three nodes: each one stopped (SIGTERM) and started again in turn
while a client issues in a loop through the two others with one session. No issuance is lost or
made twice, the session survives every restart (sessions in the database), and the leadership
moves once per stop of the leader, never otherwise.
"""
import threading

import pytest
import requests

from tests.ha.cluster import (READY_TIMEOUT, create_ca, lock_acquisitions, node_counts,
                              single_leader, wait_until)

pytestmark = [pytest.mark.ha, node_counts(3)]


class Writer(threading.Thread):
    """Issues one certificate at a time through the nodes not named in `down`."""

    def __init__(self, admin, nodes, ca_id):
        super().__init__(daemon=True)
        self.clients = {node.name: admin.on(node) for node in nodes}
        self.ca_id, self.down, self.done = ca_id, None, threading.Event()
        self.outcomes, self._cond = [], threading.Condition()

    def run(self):
        n = 0
        while not self.done.is_set():
            names = [name for name in self.clients if name != self.down]
            name = names[n % len(names)]
            n += 1
            cn = f'rolling-{n}.ucm-ha.test'
            try:
                r = self.clients[name].post('/api/v2/certificates',
                                            {'cn': cn, 'ca_id': self.ca_id, 'validity_days': 30})
                outcome = (name, cn, r.status_code, r.json().get('data') if r.ok else r.text[:300])
            except requests.RequestException as e:
                outcome = (name, cn, None, repr(e))
            with self._cond:
                self.outcomes.append(outcome)
                self._cond.notify_all()

    def avoid(self, node):
        """From now on no request goes to `node`; returns once the one in flight is answered."""
        with self._cond:
            self.down = None if node is None else node.name
            seen = len(self.outcomes)
            assert self._cond.wait_for(lambda: len(self.outcomes) >= seen + 1, 120), 'writer stalled'


def test_rolling_restart_while_a_client_issues(cluster, admin):
    wait_until(lambda: single_leader(cluster.nodes), 60, 'one leader')
    ca = create_ca(admin, 'HA rolling restart CA')
    writer = Writer(admin, cluster.nodes, ca['id'])
    writer.start()
    leader_stops = 0
    try:
        for node in cluster.nodes:
            writer.avoid(node)
            was_leader = node.health()['leader'] is True
            leader_stops += was_leader
            node.stop()
            assert node.proc.returncode is not None
            node.start()
            wait_until(node.ready, READY_TIMEOUT, f'node {node.name} ready again')
            wait_until(lambda: single_leader(cluster.nodes), 60, f'one leader after {node.name}')
            writer.avoid(None)
            # The session issued on the restarted node too, once it serves again
            with writer._cond:
                seen = len(writer.outcomes)
                assert writer._cond.wait_for(
                    lambda: any(o[0] == node.name for o in writer.outcomes[seen:]), 120), node.name
    finally:
        writer.done.set()
        writer.join(150)

    outcomes = writer.outcomes
    failed = [o for o in outcomes if o[2] not in (200, 201)]
    assert not failed, failed
    for node in cluster.nodes:
        assert any(o[0] == node.name for o in outcomes), node.name
    rows = cluster.sql('SELECT id, serial_number FROM certificates WHERE caref = %s', (ca['refid'],))
    # Nothing lost, nothing twice: one row per answered request, each under its own serial
    assert sorted(cert_id for cert_id, _ in rows) == sorted(o[3]['id'] for o in outcomes)
    assert len({serial for _, serial in rows}) == len(rows) == len(outcomes)
    (count,), = cluster.sql('SELECT serial FROM certificate_authorities WHERE id = %s', (ca['id'],))
    assert count == len(rows)
    # The session of before the restarts still works on every node
    for node in cluster.nodes:
        r = admin.on(node).get('/api/v2/auth/verify')
        assert r.status_code == 200 and r.json()['data'].get('authenticated') is not False, r.text[:300]
    # One acquisition at start, then one per stop of the leader
    assert sum(lock_acquisitions(n) for n in cluster.nodes) == 1 + leader_stops
    assert leader_stops >= 1
