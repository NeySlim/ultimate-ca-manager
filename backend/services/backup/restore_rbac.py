"""RBAC restore methods mixin for BackupService.

Each section is applied through `apply_columns`, from the manifest the export
was written from, so a column added to one of these models comes back without
anyone having to remember this file exists. The hand-written lists were
already behind: a certificate template came back without its EKU or its key
size, a trusted certificate without its validity dates, and a group without
the columns added after the list was written.

`plan` is what turns a reference into the row it names *here*. None of these
sections declares one, so nothing is ever resolved and an empty plan answers
everything `apply_columns` asks; the parameter is there so the restore can
hand its own down the day one of them does.
"""
import logging
from typing import Dict, Optional

from models import db

from .restore import RestorePlan
from .restore.apply import apply_columns

logger = logging.getLogger(__name__)


class RestoreRbacMixin:
    def _restore_groups(self, backup_data: Dict, results: Dict,
                        plan: Optional[RestorePlan] = None) -> None:
        """Restore groups from backup data.

        The nested `members` are not a column of the group: they are the
        `group_members` section, mirrored inside their group for archives
        written before it existed. They stay hand-written here so such an
        archive still restores its memberships; a current archive carries the
        flat section and the manifest-driven pass applies it.
        """
        from models.group import Group, GroupMember
        plan = plan if plan is not None else RestorePlan()
        for grp_data in backup_data.get('groups', []):
            group = Group.query.filter_by(name=grp_data['name']).first()
            created = group is None
            if created:
                group = Group(name=grp_data['name'])
                db.session.add(group)
            apply_columns(group, 'groups', grp_data, plan)
            if created:
                db.session.flush()   # the members below need the group's id

            # Restore members
            for m_data in grp_data.get('members', []):
                existing_m = GroupMember.query.filter_by(
                    group_id=group.id, user_id=m_data['user_id']
                ).first()
                if not existing_m:
                    db.session.add(GroupMember(
                        group_id=group.id,
                        user_id=m_data['user_id'],
                    ))
            results['groups'] += 1

    def _restore_custom_roles(self, backup_data: Dict, results: Dict,
                              plan: Optional[RestorePlan] = None) -> None:
        """Restore custom roles from backup data.

        A role can be built on another role, which is a number: the restored
        role inherited from whichever role happened to hold it here. It is a
        reference now, and the roles of this same archive are indexed again
        before the first one is written, since a role may inherit from one
        the restore is creating a few rows earlier.
        """
        from models.rbac import CustomRole
        from .restore_extended import reindex_reference_targets

        plan = plan if plan is not None else RestorePlan.build(backup_data)
        for role_data in backup_data.get('custom_roles', []):
            role = CustomRole.query.filter_by(name=role_data['name']).first()
            if role is None:
                role = CustomRole(name=role_data['name'])   # NOT NULL
                db.session.add(role)
            apply_columns(role, 'custom_roles', role_data, plan)
            results['custom_roles'] += 1
        # The roles now exist, so a role built on one of them can be placed.
        reindex_reference_targets('custom_roles', plan)
        for role_data in backup_data.get('custom_roles', []):
            if role_data.get('inherits_from') is None:
                continue
            role = CustomRole.query.filter_by(name=role_data['name']).first()
            if role is not None:
                role.inherits_from = plan.resolve(
                    'custom_roles', role_data, 'inherits_from')

    def _restore_templates(self, backup_data: Dict, results: Dict,
                           plan: Optional[RestorePlan] = None) -> None:
        """Restore certificate templates from backup data.

        Ten columns were applied out of a model that holds far more, so a
        restored template kept the target's key size, EKU, SANs and policy
        while carrying the archive's name.
        """
        from models.certificate_template import CertificateTemplate as CT
        plan = plan if plan is not None else RestorePlan()
        for t_data in backup_data.get('certificate_templates', []):
            template = CT.query.filter_by(name=t_data['name']).first()
            if template is None:
                # name, template_type and extensions_template are NOT NULL
                template = CT(
                    name=t_data['name'],
                    template_type=t_data.get('template_type') or 'custom',
                    extensions_template=t_data.get('extensions_template') or '{}')
                db.session.add(template)
            apply_columns(template, 'certificate_templates', t_data, plan)
            results['certificate_templates'] += 1

    def _restore_truststore(self, backup_data: Dict, results: Dict,
                            plan: Optional[RestorePlan] = None) -> None:
        """Restore trusted certificates from backup data.

        An existing entry had five columns written onto it, so it kept the
        target's subject, issuer, serial and validity dates while holding the
        archive's PEM: a row describing a certificate it was not.
        """
        from models.truststore import TrustedCertificate
        plan = plan if plan is not None else RestorePlan()
        for tc_data in backup_data.get('trusted_certificates', []):
            trusted = TrustedCertificate.query.filter_by(
                fingerprint_sha256=tc_data['fingerprint_sha256']
            ).first()
            if trusted is None:
                # name, certificate_pem and fingerprint_sha256 are NOT NULL
                trusted = TrustedCertificate(
                    fingerprint_sha256=tc_data['fingerprint_sha256'],
                    name=tc_data.get('name') or '',
                    certificate_pem=tc_data.get('certificate_pem') or '')
                db.session.add(trusted)
            apply_columns(trusted, 'trusted_certificates', tc_data, plan)
            results['trusted_certificates'] += 1
