"""
Discovery Models — ScanProfile, ScanRun, DiscoveredCertificate
"""
import json
from datetime import datetime, timezone
from models import db


class ScanProfile(db.Model):
    """Saved scan configuration with optional scheduling."""
    __tablename__ = 'discovery_scan_profiles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    description = db.Column(db.Text)
    targets = db.Column(db.Text, nullable=False, default='[]')
    ports = db.Column(db.Text, nullable=False, default='[443]')
    schedule_enabled = db.Column(db.Boolean, nullable=False, default=False)
    schedule_interval_minutes = db.Column(db.Integer, nullable=False, default=1440)
    notify_on_new = db.Column(db.Boolean, nullable=False, default=True)
    notify_on_change = db.Column(db.Boolean, nullable=False, default=True)
    notify_on_expiry = db.Column(db.Boolean, nullable=False, default=True)
    timeout = db.Column(db.Integer, nullable=False, default=5)
    max_workers = db.Column(db.Integer, nullable=False, default=20)
    resolve_dns = db.Column(db.Boolean, nullable=False, default=False)
    last_scan_at = db.Column(db.DateTime)
    next_scan_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    runs = db.relationship('ScanRun', backref='profile', lazy='dynamic')
    discovered = db.relationship('DiscoveredCertificate', backref='profile', lazy='dynamic')

    @property
    def targets_list(self):
        try:
            return json.loads(self.targets) if self.targets else []
        except (json.JSONDecodeError, TypeError):
            return []

    @targets_list.setter
    def targets_list(self, val):
        self.targets = json.dumps(val) if val else '[]'

    @property
    def ports_list(self):
        try:
            return json.loads(self.ports) if self.ports else [443]
        except (json.JSONDecodeError, TypeError):
            return [443]

    @ports_list.setter
    def ports_list(self, val):
        self.ports = json.dumps(val) if val else '[443]'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'targets': self.targets_list,
            'ports': self.ports_list,
            'schedule_enabled': self.schedule_enabled,
            'schedule_interval_minutes': self.schedule_interval_minutes,
            'notify_on_new': self.notify_on_new,
            'notify_on_change': self.notify_on_change,
            'notify_on_expiry': self.notify_on_expiry,
            'timeout': self.timeout,
            'max_workers': self.max_workers,
            'resolve_dns': self.resolve_dns,
            'last_scan_at': self.last_scan_at.isoformat() if self.last_scan_at else None,
            'next_scan_at': self.next_scan_at.isoformat() if self.next_scan_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ScanRun(db.Model):
    """Record of a single scan execution."""
    __tablename__ = 'discovery_scan_runs'

    id = db.Column(db.Integer, primary_key=True)
    scan_profile_id = db.Column(db.Integer, db.ForeignKey('discovery_scan_profiles.id', ondelete='SET NULL'))
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime)
    status = db.Column(db.String(32), nullable=False, default='running')
    total_targets = db.Column(db.Integer, nullable=False, default=0)
    targets_scanned = db.Column(db.Integer, nullable=False, default=0)
    certs_found = db.Column(db.Integer, nullable=False, default=0)
    new_certs = db.Column(db.Integer, nullable=False, default=0)
    changed_certs = db.Column(db.Integer, nullable=False, default=0)
    errors = db.Column(db.Integer, nullable=False, default=0)
    triggered_by = db.Column(db.String(32), nullable=False, default='manual')
    triggered_by_user = db.Column(db.String(100))
    timeout = db.Column(db.Integer, nullable=False, default=5)
    max_workers = db.Column(db.Integer, nullable=False, default=20)
    resolve_dns = db.Column(db.Boolean, nullable=False, default=False)

    @property
    def duration_seconds(self):
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self):
        return {
            'id': self.id,
            'scan_profile_id': self.scan_profile_id,
            'profile_name': self.profile.name if self.profile else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'status': self.status,
            'total_targets': self.total_targets,
            'targets_scanned': self.targets_scanned,
            'certs_found': self.certs_found,
            'new_certs': self.new_certs,
            'changed_certs': self.changed_certs,
            'errors': self.errors,
            'triggered_by': self.triggered_by,
            'triggered_by_user': self.triggered_by_user,
            'timeout': self.timeout,
            'max_workers': self.max_workers,
            'resolve_dns': self.resolve_dns,
            'duration_seconds': self.duration_seconds,
        }


class DiscoveredCertificate(db.Model):
    """Certificate discovered via TLS network scan."""
    __tablename__ = 'discovered_certificates'

    id = db.Column(db.Integer, primary_key=True)
    scan_profile_id = db.Column(db.Integer, db.ForeignKey('discovery_scan_profiles.id', ondelete='SET NULL'))
    target = db.Column(db.String(1024), nullable=False)
    port = db.Column(db.Integer, nullable=False, default=443)
    sni_hostname = db.Column(db.String(1024), nullable=False, default='')
    subject = db.Column(db.Text)
    issuer = db.Column(db.Text)
    serial_number = db.Column(db.String(100))
    not_before = db.Column(db.DateTime)
    not_after = db.Column(db.DateTime)
    fingerprint_sha256 = db.Column(db.String(64), index=True)
    pem_certificate = db.Column(db.Text)
    status = db.Column(db.String(32), nullable=False, default='unmanaged')
    ucm_certificate_id = db.Column(db.Integer, db.ForeignKey('certificates.id', ondelete='SET NULL'))
    first_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_changed_at = db.Column(db.DateTime)
    previous_fingerprint = db.Column(db.String(64))
    dns_hostname = db.Column(db.String(1024))
    san_dns_names = db.Column(db.Text, nullable=False, default='[]')
    san_ip_addresses = db.Column(db.Text, nullable=False, default='[]')
    scan_error = db.Column(db.Text)

    ucm_certificate = db.relationship('Certificate', backref='discovered_instances')

    __table_args__ = (
        db.UniqueConstraint('target', 'port', 'sni_hostname', name='uq_disc_cert_target_port_sni'),
    )

    @property
    def is_expired(self):
        if not self.not_after:
            return False
        na = self.not_after
        if na.tzinfo is None:
            na = na.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > na

    @property
    def days_until_expiry(self):
        if not self.not_after:
            return None
        na = self.not_after
        if na.tzinfo is None:
            na = na.replace(tzinfo=timezone.utc)
        return (na - datetime.now(timezone.utc)).days

    def to_dict(self):
        return {
            'id': self.id,
            'scan_profile_id': self.scan_profile_id,
            'target': self.target,
            'port': self.port,
            'sni_hostname': self.sni_hostname or None,
            'subject': self.subject,
            'issuer': self.issuer,
            'serial_number': self.serial_number,
            'not_before': self.not_before.isoformat() if self.not_before else None,
            'not_after': self.not_after.isoformat() if self.not_after else None,
            'fingerprint_sha256': self.fingerprint_sha256,
            'status': self.status,
            'ucm_certificate_id': self.ucm_certificate_id,
            'first_seen': self.first_seen.isoformat() if self.first_seen else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'last_changed_at': self.last_changed_at.isoformat() if self.last_changed_at else None,
            'previous_fingerprint': self.previous_fingerprint,
            'dns_hostname': self.dns_hostname,
            'san_dns_names': json.loads(self.san_dns_names) if self.san_dns_names else [],
            'san_ip_addresses': json.loads(self.san_ip_addresses) if self.san_ip_addresses else [],
            'is_expired': self.is_expired,
            'days_until_expiry': self.days_until_expiry,
            'scan_error': self.scan_error,
        }
