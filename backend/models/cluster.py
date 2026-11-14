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


class SchedulerRequest(db.Model):
    """A "run now" asked on any node, claimed once by the leader (taken_at), deleted after the run."""
    __tablename__ = 'scheduler_requests'

    id = db.Column(db.Integer, primary_key=True)
    task_name = db.Column(db.String(100), nullable=False)
    requested_at = db.Column(db.DateTime, nullable=False)
    requested_by = db.Column(db.String(255))
    taken_at = db.Column(db.DateTime, index=True)
