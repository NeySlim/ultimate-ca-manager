"""HA rolling update: the nodes install the target version one at a time.

The campaign is one JSON value in system_config (CAMPAIGN_KEY). Every step is a
compare-and-set of that value: two coordinators, or two processes of one node, never
take the same step twice. The coordinator (campaign_tick, run by the scheduler leader)
sends the cluster command ``update`` to one node; that node downloads and verifies the
package itself, then asks its own host-local install (run_local_turn). The next node
starts only once the previous one beats fresh on the target version; a node that does
not come back within NODE_GUARD_SECONDS stops the campaign until an admin resumes it.
"""
import json
import logging
import uuid
from collections import namedtuple
from copy import deepcopy
from datetime import datetime

logger = logging.getLogger('ucm.updates')

CAMPAIGN_KEY = 'ha_update_campaign'
# Sized for a download (300 s is the timeout of each read, not of the whole transfer), the
# dpkg/rpm install, migrations under the boot lock (120 s) and the first heartbeat (60 s pass);
# a turn the guard stopped mid-download installs nothing (run_local_turn re-checks it)
NODE_GUARD_SECONDS = 900

RUNNING, STOPPED, DONE = 'running', 'stopped', 'done'
DISPATCHED, INSTALLING, REQUESTED = 'dispatched', 'installing', 'requested'

NodeView = namedtuple('NodeView', 'started_at heartbeat_at version')


def _dump(campaign):
    return json.dumps(campaign, sort_keys=True)


def _iso(dt):
    return dt.isoformat()


def _parse(text):
    return datetime.fromisoformat(text)


def read_campaign():
    """(stored text, campaign dict) or (None, None)."""
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=CAMPAIGN_KEY).first()
    if row is None or not row.value:
        return (row.value if row else None), None
    try:
        return row.value, json.loads(row.value)
    except ValueError:
        logger.error("Rolling update: stored campaign unreadable, ignored")
        return row.value, None


def public_view(campaign):
    if campaign is None:
        return None
    keys = ('id', 'status', 'target', 'initiated_by', 'started_at', 'finished_at', 'order',
            'skipped', 'done', 'current', 'failed')
    return {k: deepcopy(campaign.get(k)) for k in keys}


def _stale_seconds():
    from services.scheduler_leader import STALE_PASSES
    from services.scheduler_service import WAKE_INTERVAL_SECONDS
    return STALE_PASSES * WAKE_INTERVAL_SECONDS


def _nodes():
    from models import ClusterNode
    return {n.node_id: NodeView(n.started_at, n.heartbeat_at, n.version) for n in ClusterNode.query.all()}


def _fresh(view, now, stale_seconds):
    return view is not None and (now - view.heartbeat_at).total_seconds() <= stale_seconds


def _stopped(campaign, node, reason, now):
    campaign.update(status=STOPPED, current=None,
                    failed={'node': node, 'reason': reason, 'at': _iso(now)})
    return campaign, ('stopped', node, reason)


def plan_step(campaign, nodes, now, *, stale_seconds, guard):
    """The next step of a running campaign: (new campaign, (event, node, reason)) or (None, None).

    Pure: ``nodes`` maps node_id to NodeView, ``now`` is on the cluster clock.
    """
    from services.updates import versions_match
    if campaign is None or campaign.get('status') != RUNNING:
        return None, None
    c = deepcopy(campaign)
    target = c['target']
    current = c.get('current')
    if current:
        node = current['node']
        since = _parse(current['since'])
        view = nodes.get(node)
        if _fresh(view, now, stale_seconds):
            if versions_match(view.version, target):
                c['done'].append(node)
                c['current'] = None
                return c, ('node_done', node, None)
            if view.started_at > since:
                return _stopped(c, node, f"node {node} came back on version {view.version}, "
                                         f"not {target}", now)
        if (now - since).total_seconds() > guard:
            return _stopped(c, node, f"node {node} not back on version {target} "
                                     f"within {guard:.0f}s", now)
        return None, None
    following = next((n for n in c['order'] if n not in c['done']), None)
    if following is None:
        c.update(status=DONE, finished_at=_iso(now))
        return c, ('finished', None, None)
    view = nodes.get(following)
    if not _fresh(view, now, stale_seconds):
        return _stopped(c, following, f"node {following} has no fresh heartbeat", now)
    if versions_match(view.version, target):
        c['done'].append(following)
        return c, ('node_done', following, None)
    c['current'] = {'node': following, 'since': _iso(now), 'state': DISPATCHED}
    return c, ('dispatch', following, None)


def _command_payload(campaign):
    """What a node needs to fetch and verify the package itself; never a secret."""
    return {'campaign': campaign['id'], 'version': campaign['target'],
            'download_url': campaign['download_url'], 'package_name': campaign['package_name'],
            'sha256': campaign['sha256']}


_MESSAGES = {
    'started': "Rolling update to {target} started",
    'resumed': "Rolling update to {target} resumed",
    'dispatch': "Rolling update to {target}: node {node} is next",
    'installing': "Rolling update to {target}: node {node} downloaded and verified the package, "
                  "install requested",
    'node_done': "Rolling update to {target}: node {node} is back on the new version",
    'finished': "Rolling update to {target} finished on every node",
    'stopped': "Rolling update to {target} stopped at node {node}: {reason}",
}


def _announce(campaign, event, actor=None):
    """Audit, log and real-time event for one step; never raises."""
    kind, node, reason = event
    message = _MESSAGES[kind].format(target=campaign['target'], node=node, reason=reason)
    failed = kind == 'stopped'
    (logger.error if failed else logger.info)(message)
    try:
        from services.audit_service import AuditService
        AuditService.log_action(action='settings_update', resource_type='system', resource_id='ucm',
                                resource_name='UCM Rolling Update', details=message,
                                success=not failed, username=actor or campaign.get('initiated_by'))
    except Exception as e:
        logger.error(f"Rolling update step not audited: {type(e).__name__}: {e}")
    try:
        from websocket.emitters import on_system_alert
        on_system_alert('update_campaign', message, 'critical' if failed else 'info',
                        {'campaign': public_view(campaign)})
    except Exception as e:
        logger.warning(f"Rolling update event not sent: {type(e).__name__}: {e}")


def _store(raw, campaign):
    """Compare-and-set; on a lost race the session (and a command added to it) is rolled back."""
    from models import db
    from utils.config_cas import config_compare_and_set
    if config_compare_and_set(CAMPAIGN_KEY, raw, _dump(campaign)):
        return True
    db.session.rollback()
    return False


def start_campaign(target, download_url, package_name, sha256, initiated_by):
    """(started, message, campaign): one campaign at a time, over the nodes beating now."""
    from services.scheduler_leader import cluster_utc_now
    if not sha256:
        return False, "No SHA-256 published for this package: a rolling update installs only verified packages", None
    if not download_url or not package_name:
        return False, "No package for this platform", None
    raw, current = read_campaign()
    if current is not None and current.get('status') == RUNNING:
        return False, f"A rolling update to {current['target']} is already running", current
    now = cluster_utc_now()
    stale = _stale_seconds()
    nodes = _nodes()
    order = sorted(n for n, v in nodes.items() if _fresh(v, now, stale))
    if not order:
        return False, "No node beats in the cluster", None
    campaign = {'id': uuid.uuid4().hex, 'status': RUNNING, 'target': target,
                'download_url': download_url, 'package_name': package_name, 'sha256': sha256.lower(),
                'initiated_by': initiated_by, 'started_at': _iso(now), 'finished_at': None,
                'order': order, 'skipped': sorted(set(nodes) - set(order)), 'done': [],
                'current': None, 'failed': None}
    if not _store(raw, campaign):
        return False, "Another rolling update was started at the same time", None
    _announce(campaign, ('started', None, None), initiated_by)
    return True, f"Rolling update to {target} started: the nodes update one at a time", campaign


def resume_campaign(actor):
    """A stopped campaign goes on from the node that failed, once an admin fixed it."""
    raw, campaign = read_campaign()
    if campaign is None or campaign.get('status') != STOPPED:
        return False, "No stopped rolling update to resume", campaign
    resumed = deepcopy(campaign)
    resumed.update(status=RUNNING, current=None, failed=None)
    if not _store(raw, resumed):
        return False, "The rolling update changed meanwhile: reload its state", None
    _announce(resumed, ('resumed', None, None), actor)
    return True, f"Rolling update to {resumed['target']} resumed", resumed


def campaign_tick(now=None):
    """Coordinator step (scheduler leader, and right after a start or resume): the event taken or None."""
    from services.scheduler_leader import cluster_utc_now
    raw, campaign = read_campaign()
    if campaign is None or campaign.get('status') != RUNNING:
        return None
    new, event = plan_step(campaign, _nodes(), now or cluster_utc_now(),
                           stale_seconds=_stale_seconds(), guard=NODE_GUARD_SECONDS)
    if new is None:
        return None
    if event[0] == 'dispatch':
        from services.cluster_commands import UPDATE, emit
        # In the transaction of the step: the turn exists only with its command
        emit(UPDATE, _command_payload(new), target=event[1])
    if not _store(raw, new):
        return None
    _announce(new, event)
    return event


def _stop(raw, campaign, node, reason):
    from services.scheduler_leader import cluster_utc_now
    stopped, event = _stopped(deepcopy(campaign), node, reason, cluster_utc_now())
    if _store(raw, stopped):
        _announce(stopped, event)


def _discard(path):
    import os
    try:
        os.remove(path)
    except OSError as e:
        logger.warning(f"Rolling update: dropped package not removed: {type(e).__name__}: {e}")


def run_local_turn(payload, node_id=None, version=None):
    """Handler of the ``update`` command on the node it targets: verified download, then
    the host-local install request. Runs once per turn, whatever process gets there first."""
    from config.settings import Config
    from services import updates
    node_id = node_id or Config.NODE_ID
    version = version or Config.APP_VERSION
    payload = payload or {}
    raw, campaign = read_campaign()
    if campaign is None or campaign.get('id') != payload.get('campaign') \
            or campaign.get('status') != RUNNING:
        return
    current = campaign.get('current') or {}
    if current.get('node') != node_id or current.get('state') != DISPATCHED:
        return  # not this node's turn, or already taken (replay, sibling process)
    if updates.versions_match(version, campaign['target']):
        return  # already there: the coordinator counts it done on its next step
    taken = deepcopy(campaign)
    taken['current']['state'] = INSTALLING
    if not _store(raw, taken):
        return
    raw = _dump(taken)
    sha256 = payload.get('sha256')
    if not sha256 or sha256.lower() != campaign['sha256']:
        return _stop(raw, taken, node_id, "the command carries no matching SHA-256: install refused")
    try:
        path = updates.download_update(payload['download_url'], payload['package_name'],
                                       expected_sha256=sha256)
    except Exception as e:
        return _stop(raw, taken, node_id, str(e)[:300])
    # The turn must still be ours after the download: a campaign stopped meanwhile installs nothing
    requested = deepcopy(taken)
    requested['current']['state'] = REQUESTED
    if not _store(raw, requested):
        _discard(path)
        logger.error(f"Rolling update: campaign changed during the download on {node_id}, "
                     f"package dropped and not installed")
        return
    raw = _dump(requested)
    try:
        updates.install_update(path, to_version=campaign['target'],
                               initiated_by=campaign.get('initiated_by') or 'system')
    except Exception as e:
        return _stop(raw, requested, node_id, str(e)[:300])
    _announce(requested, ('installing', node_id, None))
