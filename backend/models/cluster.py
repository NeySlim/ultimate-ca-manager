"""HA cluster state shared through the database (migration 141)."""
from models import db


class ClusterNode(db.Model):
    """One row per node, refreshed by its scheduler process on every pass."""
    __tablename__ = 'cluster_nodes'

    node_id = db.Column(db.String(255), primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False)
    heartbeat_at = db.Column(db.DateTime, nullable=False)
    is_leader = db.Column(db.Boolean, nullable=False, default=False)
    version = db.Column(db.String(32))
    # NULL once the node stopped cleanly (gunicorn on_exit): a full-stop migration does not wait for it
    pid = db.Column(db.Integer)
    # deb, rpm-el9, rpm-fedora, container or unknown: the package a rolling update gives this node
    package_family = db.Column(db.String(32))
    # Last cluster_commands.id this node's applier handled (migration 143)
    command_seen = db.Column(db.Integer)
    # Last restart command this node claimed: one process of the node acts on it (migration 143)
    restart_seen = db.Column(db.Integer)
    # Fingerprint of the node's key-encryption key, never the key itself
    kek_fingerprint = db.Column(db.String(16))
    # Random per node process: a fresh row with another token means the identifier is taken
    instance_token = db.Column(db.String(64))
    # Token of the cluster maintenance the web worker, and the process running the
    # scheduled tasks, last refused writes for (services.cluster_maintenance)
    maintenance_ack = db.Column(db.String(36))
    maintenance_ack_scheduler = db.Column(db.String(36))


class ClusterCommand(db.Model):
    """A reload or restart for every node (node_id NULL) or one node, emitted in the
    transaction that changed the setting; purged by the leader after 24 hours."""
    __tablename__ = 'cluster_commands'

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(64), nullable=False)
    payload = db.Column(db.Text)  # JSON
    created_at = db.Column(db.DateTime, nullable=False, index=True)
    created_by = db.Column(db.String(255))
    node_id = db.Column(db.String(255))


class ClusterMaintenance(db.Model):
    """At most one row (id 1): while it holds and its lease runs, no node writes."""
    __tablename__ = 'cluster_maintenance'

    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    token = db.Column(db.String(36), nullable=False)
    reason = db.Column(db.String(16), nullable=False)  # restore or manual
    phase = db.Column(db.String(16), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    # Set when the rolling restart is asked: a process started after it serves again
    restored_at = db.Column(db.DateTime)
    node_id = db.Column(db.String(255))
    actor = db.Column(db.String(255))


class SchedulerRequest(db.Model):
    """A "run now" asked on any node, claimed once by the leader (taken_at), deleted after the run."""
    __tablename__ = 'scheduler_requests'

    id = db.Column(db.Integer, primary_key=True)
    task_name = db.Column(db.String(100), nullable=False)
    requested_at = db.Column(db.DateTime, nullable=False)
    requested_by = db.Column(db.String(255))
    taken_at = db.Column(db.DateTime, index=True)
