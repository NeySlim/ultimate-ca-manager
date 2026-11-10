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


class SchedulerRequest(db.Model):
    """A "run now" asked on any node, claimed once by the leader (taken_at), deleted after the run."""
    __tablename__ = 'scheduler_requests'

    id = db.Column(db.Integer, primary_key=True)
    task_name = db.Column(db.String(100), nullable=False)
    requested_at = db.Column(db.DateTime, nullable=False)
    requested_by = db.Column(db.String(255))
    taken_at = db.Column(db.DateTime, index=True)
