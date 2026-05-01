"""
RBAC restore methods mixin for BackupService
"""
import base64
import logging
from typing import Dict, Any

from models import db

logger = logging.getLogger(__name__)


class RestoreRbacMixin:
    def _restore_groups(self, backup_data: Dict, results: Dict) -> None:
        """Restore groups from backup data"""
        from models.group import Group, GroupMember
        for grp_data in backup_data.get('groups', []):
            existing = Group.query.filter_by(name=grp_data['name']).first()
            if existing:
                existing.description = grp_data.get('description')
                existing.permissions = grp_data.get('permissions')
                group = existing
            else:
                group = Group(
                    name=grp_data['name'],
                    description=grp_data.get('description'),
                    permissions=grp_data.get('permissions'),
                )
                db.session.add(group)
                db.session.flush()
            # Restore members
            for m_data in grp_data.get('members', []):
                existing_m = GroupMember.query.filter_by(
                    group_id=group.id, user_id=m_data['user_id']
                ).first()
                if not existing_m:
                    db.session.add(GroupMember(
                        group_id=group.id,
                        user_id=m_data['user_id'],
                        role=m_data.get('role', 'member'),
                    ))
            results['groups'] += 1

    def _restore_custom_roles(self, backup_data: Dict, results: Dict) -> None:
        """Restore custom roles from backup data"""
        from models.rbac import CustomRole
        for role_data in backup_data.get('custom_roles', []):
            existing = CustomRole.query.filter_by(name=role_data['name']).first()
            if existing:
                existing.description = role_data.get('description')
                existing.permissions = role_data.get('permissions')
                existing.is_system = role_data.get('is_system', False)
            else:
                new_role = CustomRole(
                    name=role_data['name'],
                    description=role_data.get('description'),
                    permissions=role_data.get('permissions'),
                    is_system=role_data.get('is_system', False),
                )
                db.session.add(new_role)
            results['custom_roles'] += 1

    def _restore_templates(self, backup_data: Dict, results: Dict) -> None:
        """Restore certificate templates from backup data"""
        from models.certificate_template import CertificateTemplate as CT
        for t_data in backup_data.get('certificate_templates', []):
            existing = CT.query.filter_by(name=t_data['name']).first()
            if existing:
                existing.description = t_data.get('description')
                existing.template_type = t_data.get('template_type')
                existing.key_type = t_data.get('key_type')
                existing.validity_days = t_data.get('validity_days')
                existing.digest = t_data.get('digest')
                existing.dn_template = t_data.get('dn_template')
                existing.extensions_template = t_data.get('extensions_template')
                existing.is_system = t_data.get('is_system', False)
                existing.is_active = t_data.get('is_active', True)
            else:
                new_t = CT(
                    name=t_data['name'],
                    description=t_data.get('description'),
                    template_type=t_data.get('template_type', 'custom'),
                    key_type=t_data.get('key_type'),
                    validity_days=t_data.get('validity_days'),
                    digest=t_data.get('digest'),
                    dn_template=t_data.get('dn_template'),
                    extensions_template=t_data.get('extensions_template', '{}'),
                    is_system=t_data.get('is_system', False),
                    is_active=t_data.get('is_active', True),
                    created_by=t_data.get('created_by'),
                )
                db.session.add(new_t)
            results['certificate_templates'] += 1

    def _restore_truststore(self, backup_data: Dict, results: Dict) -> None:
        """Restore trusted certificates from backup data"""
        from models.truststore import TrustedCertificate
        for tc_data in backup_data.get('trusted_certificates', []):
            existing = TrustedCertificate.query.filter_by(
                fingerprint_sha256=tc_data['fingerprint_sha256']
            ).first()
            if existing:
                existing.name = tc_data.get('name')
                existing.description = tc_data.get('description')
                existing.certificate_pem = tc_data.get('certificate_pem')
                existing.purpose = tc_data.get('purpose')
                existing.notes = tc_data.get('notes')
            else:
                new_tc = TrustedCertificate(
                    name=tc_data.get('name', ''),
                    description=tc_data.get('description'),
                    certificate_pem=tc_data.get('certificate_pem', ''),
                    fingerprint_sha256=tc_data['fingerprint_sha256'],
                    fingerprint_sha1=tc_data.get('fingerprint_sha1'),
                    subject=tc_data.get('subject'),
                    issuer=tc_data.get('issuer'),
                    serial_number=tc_data.get('serial_number'),
                    purpose=tc_data.get('purpose'),
                    added_by=tc_data.get('added_by'),
                    notes=tc_data.get('notes'),
                )
                db.session.add(new_tc)
            results['trusted_certificates'] += 1
