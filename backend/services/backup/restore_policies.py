"""
Policy-related restore methods mixin for BackupService
"""
import logging
from typing import Dict, Any

from models import db

logger = logging.getLogger(__name__)


class RestorePoliciesMixin:
    def _restore_policies(self, backup_data: Dict, results: Dict) -> None:
        """Restore certificate policies from backup data"""
        from models.policy import CertificatePolicy
        for pol_data in backup_data.get('certificate_policies', []):
            existing = CertificatePolicy.query.filter_by(name=pol_data['name']).first()
            if existing:
                existing.description = pol_data.get('description')
                existing.policy_type = pol_data.get('policy_type')
                existing.rules = pol_data.get('rules', '{}')
                existing.requires_approval = pol_data.get('requires_approval', False)
                existing.min_approvers = pol_data.get('min_approvers', 1)
                existing.notify_on_violation = pol_data.get('notify_on_violation', True)
                existing.notification_emails = pol_data.get('notification_emails')
                existing.is_active = pol_data.get('is_active', True)
                existing.priority = pol_data.get('priority', 100)
            else:
                new_pol = CertificatePolicy(
                    name=pol_data['name'],
                    description=pol_data.get('description'),
                    policy_type=pol_data.get('policy_type', 'issuance'),
                    ca_id=pol_data.get('ca_id'),
                    template_id=pol_data.get('template_id'),
                    rules=pol_data.get('rules', '{}'),
                    requires_approval=pol_data.get('requires_approval', False),
                    approval_group_id=pol_data.get('approval_group_id'),
                    min_approvers=pol_data.get('min_approvers', 1),
                    notify_on_violation=pol_data.get('notify_on_violation', True),
                    notification_emails=pol_data.get('notification_emails'),
                    is_active=pol_data.get('is_active', True),
                    priority=pol_data.get('priority', 100),
                    created_by=pol_data.get('created_by'),
                )
                db.session.add(new_pol)
            results['certificate_policies'] += 1

    def _restore_dns_providers(self, backup_data: Dict, results: Dict) -> None:
        """Restore DNS providers from backup data"""
        from models.acme_models import DnsProvider
        for dp_data in backup_data.get('dns_providers', []):
            existing = DnsProvider.query.filter_by(name=dp_data['name']).first()
            if existing:
                existing.provider_type = dp_data.get('provider_type')
                existing.credentials = dp_data.get('credentials')
                existing.zones = dp_data.get('zones')
                existing.is_default = dp_data.get('is_default', False)
                existing.enabled = dp_data.get('enabled', True)
            else:
                new_dp = DnsProvider(
                    name=dp_data['name'],
                    provider_type=dp_data.get('provider_type', 'manual'),
                    credentials=dp_data.get('credentials'),
                    zones=dp_data.get('zones'),
                    is_default=dp_data.get('is_default', False),
                    enabled=dp_data.get('enabled', True),
                )
                db.session.add(new_dp)
            results['dns_providers'] += 1

    def _restore_acme_domains(self, backup_data: Dict, results: Dict) -> None:
        """Restore ACME domains from backup data"""
        from models.acme_models import AcmeDomain
        for ad_data in backup_data.get('acme_domains', []):
            existing = AcmeDomain.query.filter_by(domain=ad_data['domain']).first()
            if existing:
                existing.is_wildcard_allowed = ad_data.get('is_wildcard_allowed', True)
                existing.auto_approve = ad_data.get('auto_approve', True)
                existing.issuing_ca_id = ad_data.get('issuing_ca_id')
                existing.created_by = ad_data.get('created_by')
            else:
                new_ad = AcmeDomain(
                    domain=ad_data['domain'],
                    dns_provider_id=ad_data.get('dns_provider_id', 1),
                    issuing_ca_id=ad_data.get('issuing_ca_id'),
                    is_wildcard_allowed=ad_data.get('is_wildcard_allowed', True),
                    auto_approve=ad_data.get('auto_approve', True),
                    created_by=ad_data.get('created_by'),
                )
                db.session.add(new_ad)
            results['acme_domains'] += 1

    def _restore_acme_local_domains(self, backup_data: Dict, results: Dict) -> None:
        """Restore ACME local domains from backup data"""
        from models.acme_models import AcmeLocalDomain
        for ld_data in backup_data.get('acme_local_domains', []):
            existing = AcmeLocalDomain.query.filter_by(domain=ld_data['domain']).first()
            if existing:
                existing.issuing_ca_id = ld_data.get('issuing_ca_id')
                existing.auto_approve = ld_data.get('auto_approve', True)
                existing.created_by = ld_data.get('created_by')
            else:
                new_ld = AcmeLocalDomain(
                    domain=ld_data['domain'],
                    issuing_ca_id=ld_data.get('issuing_ca_id'),
                    auto_approve=ld_data.get('auto_approve', True),
                    created_by=ld_data.get('created_by'),
                )
                db.session.add(new_ld)
            results['acme_local_domains'] += 1
