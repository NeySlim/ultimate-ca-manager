"""The leader killed (SIGKILL) while its scheduled CRL pass signs a CA's CRL: another node leads
within the documented delay, the dead leader's lease holds no longer than its duration, and the
CRL is signed once more under a higher number, never two CRLs under one number.

The instant is made deterministic by a row lock: the test holds the CA's CRL number counter
(services/crl/numbering.py), runs the pass, and kills the leader once its session waits on that
row in pg_stat_activity, with the CA's lease taken in system_config.
"""
import threading
import time
from datetime import datetime

import pytest
from cryptography import x509

from services.crl_scheduler_task import CRLSchedulerTask
from services.scheduler_leader import STALE_PASSES
from services.scheduler_service import LOCK_RETRY_SECONDS, WAKE_INTERVAL_SECONDS
from tests.ha.cluster import create_ca, issue, node_counts, single_leader, wait_until
from utils.config_cas import LEASE_RETRY_MARGIN

pytestmark = [pytest.mark.ha, node_counts(3)]

TASK = 'crl_auto_regen'
# docs/ADMIN_GUIDE.md, HA mode: takeover within LOCK_RETRY_SECONDS once the dead leader's
# session is gone, a leader still named until STALE_PASSES heartbeats have passed
TAKEOVER_BOUND = LOCK_RETRY_SECONDS + STALE_PASSES * WAKE_INTERVAL_SECONDS
# docs/HA.md, Scheduled passes: a CRL pass refused by a lease runs 30 s after that lease ends;
# the leader's loop wakes at most once a pass
LEASE_SECONDS = CRLSchedulerTask.LEASE.total_seconds()
RETRY_BOUND = LEASE_SECONDS + LEASE_RETRY_MARGIN.total_seconds() + WAKE_INTERVAL_SECONDS
MARGIN = 15


def _crls(cluster, ca_id):
    return cluster.sql('SELECT crl_number, this_update, crl_der FROM crl_metadata '
                       'WHERE ca_id = %s AND is_delta = false ORDER BY crl_number', (ca_id,))


def _lease(cluster, ca_id):
    rows = cluster.sql('SELECT value FROM system_config WHERE key = %s',
                       (f'crl_schedule_lease_{ca_id}',))
    return rows[0][0] if rows else None


def _run(client):
    r = client.post(f'/api/v2/system/scheduler/{TASK}/run')
    assert r.status_code == 200, f'{client.node.name}: {r.status_code} {r.text[:500]}'
    return r.json()['data']


def test_the_leader_killed_during_a_scheduled_crl(cluster, admin):
    leader = wait_until(lambda: single_leader(cluster.nodes), 60, 'one leader')
    followers = [node for node in cluster.nodes if node is not leader]
    ca = create_ca(admin, 'HA crash CRL CA')
    for change in ({'cdp_url': 'http://ucm-ha.test/cdp/ha.crl'}, {'cdp_enabled': True}):
        r = admin.patch(f"/api/v2/cas/{ca['id']}", change)
        assert r.status_code == 200, r.text[:500]
    cert = issue(admin, ca['id'], 'revoked.ucm-ha.test')
    r = admin.post(f"/api/v2/certificates/{cert['id']}/revoke", {'reason': 'keyCompromise'})
    assert r.status_code == 200, r.text[:500]
    r = admin.post(f"/api/v2/crl/{ca['id']}/regenerate")
    assert r.status_code == 200, r.text[:500]
    before = _crls(cluster, ca['id'])
    previous = before[-1][0]
    # Past its next update: the scheduled pass must sign it again
    cluster.sql("UPDATE crl_metadata SET next_update = (now() AT TIME ZONE 'UTC') - interval '1 minute' "
                'WHERE ca_id = %s', (ca['id'],))

    asked = threading.Thread(target=lambda: _run(admin.on(followers[0])))
    with cluster.holding('SELECT issuer_key FROM crl_number_counters FOR UPDATE') as hold:
        asked.start()
        wait_until(lambda: cluster.waiting_on_lock(leader, 'crl_number_counters'), 60,
                   f'the scheduled CRL pass of {leader.name} waits on the number counter')
        stamp = _lease(cluster, ca['id'])
        assert stamp and 'Regenerating CRL for CA' in leader.app_log_text(), stamp
        leased_at = time.monotonic()
        leased_since = datetime.fromisoformat(stamp.split('|', 1)[0])
        leader.kill()
        killed_at = time.monotonic()
        hold.rollback()
    asked.join(60)

    heir = wait_until(lambda: single_leader(followers), TAKEOVER_BOUND + MARGIN, 'a follower takes over')
    assert time.monotonic() - killed_at <= TAKEOVER_BOUND + MARGIN

    # The dead leader's lease still holds: the heir leaves the CRL to it and plans one retry
    status = _run(admin.on(heir))
    assert not status.get('queued'), status
    assert f"CRL of CA {ca['id']} left to the node publishing it" in heir.app_log_text()
    assert _lease(cluster, ca['id']) == stamp
    assert _crls(cluster, ca['id']) == before

    after = wait_until(lambda: len(_crls(cluster, ca['id'])) > len(before) and _crls(cluster, ca['id']),
                       RETRY_BOUND + MARGIN - (time.monotonic() - leased_at),
                       'the CRL signed again once the lease is over')
    (number, this_update, der), = after[len(before):]
    # Signed once, after the lease ended, under the next number: the dead pass consumed none
    assert this_update >= leased_since + CRLSchedulerTask.LEASE, (this_update, leased_since)
    assert number == previous + 1, (previous, number)
    numbers = [n for n, _, _ in after]
    assert len(set(numbers)) == len(numbers), numbers
    (counter,), = cluster.sql('SELECT last_number FROM crl_number_counters')
    assert counter == number

    crl = x509.load_der_x509_crl(bytes(der))
    assert crl.extensions.get_extension_for_class(x509.CRLNumber).value.crl_number == number
    assert int(cert['serial_number']) in {entry.serial_number for entry in crl}
    # Given back by the heir's pass
    assert _lease(cluster, ca['id']) == ''
