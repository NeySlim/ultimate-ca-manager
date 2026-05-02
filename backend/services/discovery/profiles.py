"""
Profiles mixin — scan profile CRUD operations.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

from models import db, ScanProfile

from .helpers import _validate_port

logger = logging.getLogger(__name__)


class ProfilesMixin:

    def get_profiles(self) -> List[Dict]:
        rows = ScanProfile.query.order_by(ScanProfile.name).all()
        return [r.to_dict() for r in rows]

    def get_profile(self, profile_id: int) -> Optional[Dict]:
        row = ScanProfile.query.get(profile_id)
        return row.to_dict() if row else None

    def create_profile(self, data: Dict) -> Dict:
        raw_ports = data.get('ports', [443])
        valid_ports = [_validate_port(p) for p in raw_ports]
        valid_ports = [p for p in valid_ports if p > 0] or [443]
        profile = ScanProfile(
            name=data['name'].strip()[:200],
            description=data.get('description', '').strip()[:1000],
            targets=json.dumps(data.get('targets', [])),
            ports=json.dumps(valid_ports),
            schedule_enabled=data.get('schedule_enabled', False),
            schedule_interval_minutes=data.get('schedule_interval_minutes', 1440),
            notify_on_new=data.get('notify_on_new', True),
            notify_on_change=data.get('notify_on_change', True),
            notify_on_expiry=data.get('notify_on_expiry', True),
            timeout=min(max(int(data.get('timeout', 5)), 1), 30),
            max_workers=min(max(int(data.get('max_workers', 20)), 1), 50),
            resolve_dns=bool(data.get('resolve_dns', False)),
        )
        if profile.schedule_enabled:
            profile.next_scan_at = datetime.now(timezone.utc) + timedelta(
                minutes=profile.schedule_interval_minutes)
        db.session.add(profile)
        db.session.commit()
        return profile.to_dict()

    def update_profile(self, profile_id: int, data: Dict) -> Optional[Dict]:
        profile = ScanProfile.query.get(profile_id)
        if not profile:
            return None
        if 'name' in data:
            profile.name = data['name'].strip()[:200]
        if 'description' in data:
            profile.description = data['description'].strip()[:1000]
        if 'targets' in data:
            profile.targets = json.dumps(data['targets'])
        if 'ports' in data:
            valid_ports = [_validate_port(p) for p in data['ports']]
            valid_ports = [p for p in valid_ports if p > 0] or [443]
            profile.ports = json.dumps(valid_ports)
        if 'schedule_enabled' in data:
            profile.schedule_enabled = data['schedule_enabled']
        if 'schedule_interval_minutes' in data:
            profile.schedule_interval_minutes = data['schedule_interval_minutes']
        if 'notify_on_new' in data:
            profile.notify_on_new = data['notify_on_new']
        if 'notify_on_change' in data:
            profile.notify_on_change = data['notify_on_change']
        if 'notify_on_expiry' in data:
            profile.notify_on_expiry = data['notify_on_expiry']
        if 'timeout' in data:
            profile.timeout = min(max(int(data['timeout']), 1), 30)
        if 'max_workers' in data:
            profile.max_workers = min(max(int(data['max_workers']), 1), 50)
        if 'resolve_dns' in data:
            profile.resolve_dns = bool(data['resolve_dns'])
        profile.updated_at = datetime.now(timezone.utc)
        if profile.schedule_enabled and not profile.next_scan_at:
            profile.next_scan_at = datetime.now(timezone.utc) + timedelta(
                minutes=profile.schedule_interval_minutes)
        db.session.commit()
        return profile.to_dict()

    def delete_profile(self, profile_id: int) -> bool:
        profile = ScanProfile.query.get(profile_id)
        if not profile:
            return False
        db.session.delete(profile)
        db.session.commit()
        return True
