"""Policy-related restore methods mixin for BackupService.

Every section here is applied through `apply_columns`, from the manifest the
export was written from. The hand-written assignments it replaces had two
faults, and the second one is the reason an archive restored on one backend
and not on the other:

* a row already here had a hand-picked list of columns written onto it, and
  the references were not on the list: a policy kept the authority, the
  template and the approval group the target happened to point at while
  taking the archive's name, rules and approval settings -- a policy
  governing an issuance nobody asked it to govern. An ACME domain kept the
  DNS provider it had here, whatever the archive said;
* a row being created was written with the *source's* numeric ids
  (`certificate_policies.ca_id`, `acme_domains.dns_provider_id`) and left
  `relink_references` to repair them at the very end of the restore. SQLite
  enforces no foreign key, so the repair arrived in time and nobody was any
  the wiser; PostgreSQL refuses the insert as it happens, and the whole
  restore with it.

References are resolved where the row is written, against a plan re-indexed
for the sections this one points at: `certificate_policies` points at
authorities, templates and groups the same restore has just created, and
`acme_domains` at a DNS provider restored three lines above.

`credentials` is assigned by its manifest name, which is the model's own
property: it re-encrypts with this installation's database key, where writing
the column underneath would have left the DNS credentials readable.
"""
import logging
from typing import Dict, Optional

from models import db

from .restore.apply import apply_columns
from .restore.plan import RestorePlan
from .restore_extended import reindex_reference_targets

logger = logging.getLogger(__name__)


class RestorePoliciesMixin:
    def _restore_policies(self, backup_data: Dict, results: Dict,
                          plan: Optional[RestorePlan] = None) -> None:
        """Restore certificate policies from backup data."""
        from models.policy import CertificatePolicy

        rows = backup_data.get('certificate_policies', [])
        if not rows:
            return

        plan = plan if plan is not None else RestorePlan.build(backup_data)
        reindex_reference_targets('certificate_policies', plan)

        for pol_data in rows:
            policy = CertificatePolicy.query.filter_by(
                name=pol_data['name']).first()
            if policy is None:
                # name and rules are NOT NULL; both are overwritten by
                # apply_columns when the archive carries them.
                policy = CertificatePolicy(name=pol_data['name'],
                                           rules=pol_data.get('rules') or '{}')
                db.session.add(policy)
            apply_columns(policy, 'certificate_policies', pol_data, plan)
            results['certificate_policies'] += 1

    def _restore_dns_providers(self, backup_data: Dict, results: Dict,
                               plan: Optional[RestorePlan] = None) -> None:
        """Restore DNS providers from backup data.

        Five columns were applied and `created_at`/`updated_at` were not, so a
        provider came back dated from the restore. The credentials go through
        the model's property, which re-encrypts them with this installation's
        key.

        The section declares no reference, so an empty plan answers everything
        `apply_columns` asks; the parameter is there so the restore can hand
        its own down the day one does.
        """
        from models.acme_models import DnsProvider

        rows = backup_data.get('dns_providers', [])
        if not rows:
            return

        plan = plan if plan is not None else RestorePlan()

        for dp_data in rows:
            provider = DnsProvider.query.filter_by(name=dp_data['name']).first()
            if provider is None:
                # name and provider_type are NOT NULL
                provider = DnsProvider(
                    name=dp_data['name'],
                    provider_type=dp_data.get('provider_type') or 'manual')
                db.session.add(provider)
            apply_columns(provider, 'dns_providers', dp_data, plan)
            results['dns_providers'] += 1

    def _restore_acme_domains(self, backup_data: Dict, results: Dict,
                              plan: Optional[RestorePlan] = None) -> None:
        """Restore ACME domains from backup data.

        A new domain used to be pinned to `dns_provider_id` 1 when the archive
        carried none, and to the source's own number when it did: the column
        is NOT NULL and carries a foreign key, so on PostgreSQL the insert was
        refused outright, and on SQLite the domain answered challenges through
        whichever provider held that number here until `relink_references`
        repaired it. An existing domain was never repointed at all.
        """
        from models.acme_models import AcmeDomain

        rows = backup_data.get('acme_domains', [])
        if not rows:
            return

        plan = plan if plan is not None else RestorePlan.build(backup_data)
        reindex_reference_targets('acme_domains', plan)

        for ad_data in rows:
            domain = AcmeDomain.query.filter_by(domain=ad_data['domain']).first()
            if domain is None:
                # domain and dns_provider_id are NOT NULL; apply_columns
                # overwrites both, the provider with the id it has here.
                domain = AcmeDomain(
                    domain=ad_data['domain'],
                    dns_provider_id=plan.resolve('acme_domains', ad_data,
                                                 'dns_provider_id'))
                db.session.add(domain)
            if apply_columns(domain, 'acme_domains', ad_data, plan):
                results['acme_domains'] += 1

    def _restore_acme_local_domains(self, backup_data: Dict, results: Dict,
                                    plan: Optional[RestorePlan] = None) -> None:
        """Restore ACME local domains from backup data.

        The authority that signs for the zone is a number, and it used to be
        written as the archive held it: the zone came back signed by whatever
        authority happened to hold that number here, and on PostgreSQL, which
        enforces the column, the row was refused and the restore with it. It
        is a reference now, resolved against this installation's authorities
        before the first row is written. The section is otherwise applied
        whole, where four columns used to be.
        """
        from models.acme_models import AcmeLocalDomain

        rows = backup_data.get('acme_local_domains', [])
        if not rows:
            return

        plan = plan if plan is not None else RestorePlan.build(backup_data)
        reindex_reference_targets('acme_local_domains', plan)

        for ld_data in rows:
            domain = AcmeLocalDomain.query.filter_by(
                domain=ld_data['domain']).first()
            if domain is None:
                # domain and issuing_ca_id are NOT NULL; apply_columns writes
                # the resolved authority over the placeholder below, and
                # refuses the archive when it cannot place it.
                domain = AcmeLocalDomain(
                    domain=ld_data['domain'],
                    issuing_ca_id=ld_data.get('issuing_ca_id'))
                db.session.add(domain)
            if apply_columns(domain, 'acme_local_domains', ld_data, plan):
                results['acme_local_domains'] += 1
