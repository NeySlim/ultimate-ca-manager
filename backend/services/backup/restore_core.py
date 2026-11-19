"""
Core restore methods mixin for BackupService
"""
import json
import hashlib
import base64
import io
import logging
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List

from sqlalchemy.exc import DataError, IntegrityError
from models import db, CA, Certificate
from utils.datetime_utils import to_naive_utc, utc_now
from compliance_profiles import is_valid as is_valid_profile
from utils.port_zero import strip_port_zero_from_stored
from utils.signing_hash import SIGNATURE_SCHEMES
from models.acme_models import AcmeAccount
from services.file_regen_service import (
    advance_generation, insert_file_writes_suspended, keep_named_paths, record_removal_candidates,
    removals_listed, unwritable_dirs,
)

from . import container, installation
from .errors import BackupSchemaError, RestoreFilesUnwritable
from .export_generic import REFERENCE_SUFFIX
from .restore import RestorePlan, single_transaction
from .restore.transaction import checkpoint, expect_rows, tick, ticking
from .manifest import SECTIONS
from .section_store import SectionStore, section_kind, section_length
from .restore.apply import (apply_columns, apply_section, refuse_containers_in_columns,
                            relink_references)
from .restore.names import rename_clashing_rows
from .restore.orders import keep_newer_orders
from .restore.sso_providers import (name_blank_providers, refuse_archived_shared_types,
                                    settle_provider_types)
from .restore.repairs import replay_repairs
from .restore.conflict import conflict_from_integrity_error, is_value_too_long
from .restore.replace import plan_replacement, remove_after_writes, remove_before_writes
from utils import ssh_serials as SSHSerials
from .restore.setting_refs import deferred_keys, prune_doomed_settings, restore_setting_references
from .restore.settings import restore_encrypted_settings
from .restore_rbac import restore_nested_webauthn, upgrade_archived_permissions
from .restore.tsa_signer import upgrade_archived_tsa_signer
from .restore.windows_profiles import link_restored_connectors, upgrade_archived_windows_profiles

logger = logging.getLogger(__name__)


def _revocation_key(holder):
    """``revocation_order`` of a row or record: the gravest reason, then the earliest date."""
    from services.cert.issued_lookup import reason_rank
    return reason_rank(holder.revoke_reason), holder.revoked_at or datetime.max


def _kept_revocation(service, here):
    """In a merge, the revocation a certificate or CA row holds here, final or suspension, which
    only a graver archive replaces (lifting a hold is an act of its own); None otherwise.
    A lift in progress (removeFromCRL) is no revocation to keep."""
    if (not getattr(service, '_merging', False) or here is None or not here.revoked
            or here.revoke_reason == 'removeFromCRL'):
        return None
    return SimpleNamespace(revoked=True, revoked_at=here.revoked_at,
                           revoke_reason=here.revoke_reason, invalidity_at=here.invalidity_at)


def _archived_datetime(where: str, column: str, value: Any):
    """The instant the archive recorded for a row, or a refusal naming it.

    Each restorer used to parse its own dates behind `except Exception:
    return None`, so a revocation date, a validity date or an expiry the
    archive could not be read from simply became NULL: a revoked CA came
    back revoked with no date, and a certificate lost the day it stopped
    being valid, without a line anywhere saying so.

    An absent value is still absent — the column is nullable and an archive
    written before it existed says nothing about it. A value that is there
    and is not a date is the archive contradicting itself, and stops the
    restore. The message is a `BackupSchemaError` because that is the one
    the routes hand back to the administrator verbatim.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError) as exc:
        raise BackupSchemaError(
            f"Invalid backup: {where} holds {value!r} as its {column}, which "
            "is not a date. Nothing has been changed."
        ) from exc


def _archived_timestamps(row, where: str, data: Dict[str, Any]) -> None:
    """`created_at` and `updated_at` as the archive has them, for a hand-written restorer."""
    for column in ('created_at', 'updated_at'):
        if data.get(column) and hasattr(row, column):
            setattr(row, column, to_naive_utc(_archived_datetime(where, column, data[column])))


# Sections this restore path knows how to apply. The export carries more
# than this (the manifest is ahead of the restore), so what is not applied is
# reported rather than passed over: an archive holding webhook endpoints and
# deployment targets must not restore as a success that silently dropped them.
# Sections the manifest-driven applier puts back, in an order where a
# section comes after everything it points at: a membership needs its user and
# its group, a binding needs its target and its certificate.
GENERIC_SECTIONS = (
    'compromised_keys',
    'role_permissions',
    'group_members',
    'user_sso_identities',
    'webauthn_credentials',
    'ad_connector',
    'webhook_endpoints',
    'deploy_targets',
    'ca_cross_certificates',
    'deploy_bindings',
    'crl_deploy_bindings',
    'intune_apps',
    'scep_profiles',
    'windows_enrollment_profiles',
    'windows_profile_templates',
    'ca_template_pins',
    'acme_client_accounts',
    # After its proxy account, EAB credential and creator (users and
    # acme_eab_credentials have their own restorers, run before these).
    'acme_dns_update_keys',
    # The history an archive carries only when it is asked for. They were
    # listed as restored and no code path ever wrote them: the export
    # collected them, the restore counted them as applied, and they went
    # nowhere. An operator who asks for the audit log in their archive is
    # asking to get it back.
    'audit_logs',
    'discovered_certificates',
    'msca_requests',
    'scan_runs',
    'scep_requests',
)

# Certificates written are flushed and their PEMs let go by this many: the plan holds every
# row it placed until the commit, and a reader of a PEM loads it again from the transaction
PEM_RELEASE_ROWS = 1000
_PEM_COLUMNS = ('crt', 'csr', 'prv')


def _release_pems(certificates) -> None:
    db.session.flush()
    for cert in certificates:
        db.session.expire(cert, _PEM_COLUMNS)


RESTORED_SECTIONS = set(GENERIC_SECTIONS) | {
    'users', 'certificate_authorities', 'certificates', 'revoked_serials',
    'crl_number_counters', 'acme_accounts', 'acme_eab_credentials', 'configuration', 'groups',
    'custom_roles', 'certificate_templates', 'trusted_certificates',
    'sso_providers', 'hsm_providers', 'hsm_keys', 'api_keys', 'smtp_config',
    'notification_config', 'certificate_policies', 'auth_certificates',
    'dns_providers', 'acme_domains', 'acme_local_domains', 'ssh_cas',
    'ssh_certificates', 'microsoft_cas', 'msca_requests', 'scan_profiles',
    'scan_runs', 'discovered_certificates', 'approval_requests',
    'scep_requests', 'acme_client_orders', 'key_recovery_requests', 'audit_logs',
    'https_server',
}


def _carries(backup_data, name: str) -> bool:
    """Whether a section holds anything, asked of a v4 store without loading it."""
    if isinstance(backup_data, SectionStore):
        return backup_data.length(name) > 0
    return bool(backup_data.get(name))


class RestoreCoreMixin:
    def _check_payload_schema(self, backup_data: Dict[str, Any]) -> None:
        """Refuse a payload this version cannot restore.

        Archives written before the schema was versioned carry none of these
        fields; they are read as before, since their shape is the one this
        code has always handled.
        """
        metadata = backup_data.get('metadata')
        if metadata is None:
            return
        self._check_schema_version(metadata)
        self._check_section_counts(backup_data, metadata.get('sections'))
        self._check_section_digests(backup_data, metadata.get('section_digests'))

    def _check_schema_version(self, metadata: Any) -> None:
        """Refuse the metadata of an archive written for a later reader than this one."""
        if not isinstance(metadata, dict):
            raise BackupSchemaError("Invalid backup format: metadata is not an object")

        schema_version = metadata.get('schema_version')
        if schema_version is not None:
            if isinstance(schema_version, bool) or not isinstance(schema_version, int):
                raise BackupSchemaError("Invalid backup format: schema version is not a number")
            if schema_version > self.SCHEMA_VERSION:
                raise BackupSchemaError(
                    f"This backup uses schema version {schema_version}, newer than "
                    f"the {self.SCHEMA_VERSION} this server can restore. Upgrade "
                    "UCM to restore it; nothing has been changed."
                )

        required = metadata.get('min_reader_schema_version')
        if required is not None:
            if isinstance(required, bool) or not isinstance(required, int):
                raise BackupSchemaError(
                    "Invalid backup format: minimum reader version is not a number")
            if required > self.SCHEMA_VERSION:
                raise BackupSchemaError(
                    f"This backup requires a reader for schema version {required}; "
                    f"this server reads up to {self.SCHEMA_VERSION}. Nothing has "
                    "been changed."
                )

    @staticmethod
    def _check_section_digests(backup_data: Dict[str, Any], digests: Any) -> None:
        """Compare each section against the digest the archive recorded.

        The payload checksum says the archive is damaged; this says which
        section, which is what decides whether a restore is worth attempting.
        """
        if digests is None or isinstance(backup_data, SectionStore):
            return  # a v4 archive's digests were compared as its chunks were read
        if not isinstance(digests, dict):
            raise BackupSchemaError(
                "Invalid backup format: section digests are not an object")

        for name, expected in digests.items():
            if name not in backup_data:
                raise BackupSchemaError(
                    f"Incomplete backup: section '{name}' is announced but missing")
            try:
                canonical = json.dumps(backup_data[name], sort_keys=True,
                                       default=str).encode()
            except (TypeError, ValueError):
                raise BackupSchemaError(
                    f"Invalid backup format: section '{name}' cannot be read back")
            if hashlib.sha256(canonical).hexdigest() != expected:
                raise BackupSchemaError(
                    f"Corrupted backup: section '{name}' does not match the "
                    "digest recorded when it was written. Nothing has been "
                    "changed."
                )

    @staticmethod
    def _check_section_counts(backup_data: Dict[str, Any], sections: Any) -> None:
        """Compare each section against the count the archive announced."""
        if sections is None:
            return
        if not isinstance(sections, dict):
            raise BackupSchemaError("Invalid backup format: section counts are not an object")

        for name, expected in sections.items():
            if isinstance(expected, bool) or not isinstance(expected, int):
                raise BackupSchemaError(
                    f"Invalid backup format: count for section '{name}' is not a number")
            if name not in backup_data:
                raise BackupSchemaError(
                    f"Incomplete backup: section '{name}' is announced but missing")
            if section_kind(backup_data, name) not in ('list', 'mapping'):
                raise BackupSchemaError(
                    f"Invalid backup format: section '{name}' is neither a list nor "
                    "an object")
            held = section_length(backup_data, name)
            if held != expected:
                raise BackupSchemaError(
                    f"Incomplete backup: section '{name}' holds {held} entries, "
                    f"{expected} were written"
                )

    def restore_backup(self, backup_bytes: bytes, password: str, *, mode: str = 'replace') -> Dict[str, Any]:
        """Restore from an encrypted archive held in memory, any format v1 to v4.

        Args:
            backup_bytes: Encrypted backup file content
            password: Decryption password

        Returns:
            Dict with restore results
        """
        if container.format_version_of(backup_bytes) == container.FORMAT_VERSION_V4:
            return self._restore_v4(io.BytesIO(backup_bytes), password, mode)

        # Detect format from magic bytes
        if len(backup_bytes) >= 4 and backup_bytes[:4] == self.MAGIC:
            master_key, backup_data = self._decrypt_framed(backup_bytes, password)
        else:
            master_key, backup_data = self._decrypt_v1(backup_bytes, password)

        if not isinstance(backup_data, dict):
            raise BackupSchemaError("Invalid backup format: the payload is not an object")

        # Verify checksum
        saved_checksum = backup_data.pop('checksum', None)
        if saved_checksum:
            json_str = json.dumps(backup_data, indent=2, sort_keys=True)
            calc_checksum = hashlib.sha256(json_str.encode()).hexdigest()
            if calc_checksum != saved_checksum.get('value'):
                # Same family as the schema refusals: it happens before any
                # write, and the administrator needs to read what it says.
                raise BackupSchemaError(
                    "Backup checksum mismatch: the archive is corrupted. "
                    "Nothing has been changed.")

        return self._restore_payload(backup_data, master_key, mode)

    def restore_backup_from_path(self, path, password: str, *,
                                 mode: str = 'replace') -> Dict[str, Any]:
        """Restore the archive at `path`: a v4 is streamed, an older one read whole."""
        with open(path, 'rb') as stream:
            return self.restore_backup_from_stream(stream, password, mode=mode)

    def restore_backup_from_stream(self, stream, password: str, *,
                                   mode: str = 'replace') -> Dict[str, Any]:
        """Restore from a seekable binary stream positioned at the archive's start.

        v1 to v3 are bounded by BACKUP_MAX_UPLOAD_MB before they are read into
        memory; a v4 never is, its chunks are bounded one by one.
        """
        start = stream.tell()
        head = stream.read(container.HEADER_PREFIX_SIZE)
        stream.seek(start)
        if container.format_version_of(head) == container.FORMAT_VERSION_V4:
            return self._restore_v4(stream, password, mode)
        size = stream.seek(0, io.SEEK_END) - start
        stream.seek(start)
        container.refuse_oversized_size(size)
        return self.restore_backup(stream.read(), password, mode=mode)

    def _restore_v4(self, stream, password: str, mode: str) -> Dict[str, Any]:
        """Sections land on disk as their chunks are read; the restore loads them on demand."""
        with SectionStore() as store:
            master_key = self._read_v4(stream, password, store)
            return self._restore_payload(store, master_key, mode)

    def _restore_payload(self, backup_data, master_key: bytes, mode: str) -> Dict[str, Any]:
        """Everything after decryption: a payload dict, or a v4 `SectionStore`."""
        # Nothing reaches the disk before the commit; after it, a file that cannot be written
        # is only retried, so a directory this process cannot write refuses the restore here
        refused = unwritable_dirs()
        if refused:
            raise RestoreFilesUnwritable(
                "The restore was refused: this server cannot write to "
                f"{', '.join(refused)}. Nothing has been changed.")
        # Everything the payload claims about itself is checked here, before
        # the first write: a schema this version cannot read, or a section
        # holding fewer rows than the archive says it holds, must not be
        # discovered halfway through a restore.
        self._check_payload_schema(backup_data)
        refuse_containers_in_columns(backup_data, mappings=RESTORED_SECTIONS)
        self._check_serial_duplicates(backup_data)
        upgrade_archived_permissions(backup_data)
        windows_warnings: List[str] = []
        # Before the profiles: their section is what marks a 3.0 archive
        upgrade_archived_tsa_signer(backup_data)
        upgrade_archived_windows_profiles(backup_data, windows_warnings)
        if mode not in ('replace', 'merge'):
            raise BackupSchemaError(
                f"Unknown restore mode {mode!r}: use 'replace' (the archive "
                "becomes the instance) or 'merge' (the archive is added to it)")
        pruned = (self._sections_the_archive_replaces(backup_data)
                  if mode == 'replace' else set())
        # Before the plan, which finds these rows again by name.
        ambiguous_references: List[str] = []
        displaced: Dict[str, set] = {}
        # An archive of metadata alone restores nothing (no session revoked, no restart).
        # Counted before any row is left out: a provider a merge leaves out was carried.
        carried = sorted(
            name for name in SECTIONS
            if _carries(backup_data, name)
        )
        # One SSO provider per type at the end, whatever the mode (restore/sso_providers.py)
        refuse_archived_shared_types(backup_data)
        sso_warnings: List[str] = []
        name_blank_providers(backup_data, sso_warnings)
        settle_provider_types(backup_data, 'sso_providers' in pruned, sso_warnings, displaced)
        renamed_here: Dict[str, dict] = {}
        renamed = rename_clashing_rows(backup_data, ambiguous_references,
                                       replacing=frozenset(pruned), displaced=displaced,
                                       renamed_here=renamed_here)

        # Named before anything is written, so the answer can say what this
        # version will not put back even though the archive carries it.
        not_restored = sorted(
            name for name in backup_data.keys()
            if name not in ('metadata', 'checksum')
            and name not in RESTORED_SECTIONS
            and _carries(backup_data, name)
        )
        if not_restored:
            logger.warning(
                "Restore: the archive carries sections this version does not "
                "apply: %s", ', '.join(not_restored))

        # Initialize results
        results = {
            'users': 0,
            'cas': 0,
            'certificates': 0,
            'acme_accounts': 0,
            'acme_eab_credentials': 0,
            'settings': 0,
            'groups': 0,
            'custom_roles': 0,
            'certificate_templates': 0,
            'trusted_certificates': 0,
            'sso_providers': 0,
            'hsm_providers': 0,
            'api_keys': 0,
            'smtp_config': 0,
            'notification_config': 0,
            'certificate_policies': 0,
            'auth_certificates': 0,
            'dns_providers': 0,
            'acme_domains': 0,
            'acme_local_domains': 0,
            'https_server': 0,
            'revoked_serials': 0,
            'crl_number_counters': 0,
            'sections_not_restored': not_restored,
            'sections_carried': carried,
            'renamed': renamed,
            'ambiguous_references': ambiguous_references,
        }

        # A key that is not its certificate's was recorded when the archive
        # was written, deliberately rather than refused: a backup has to stay
        # possible precisely when something is wrong. What nobody did was tell
        # the operator on the way back in, so the restore produced an
        # authority that signs answers nobody can verify and said nothing.
        results['key_mismatches'] = self._archived_key_mismatches(backup_data)
        for record in results['key_mismatches']:
            logger.warning(
                "Restore: %s carries a private key that is not its "
                "certificate's; it cannot sign for this installation", record)

        # Nothing has been written yet, and nothing will be until the plan
        # is built: it decides which row here each archived row is, and what
        # each reference resolves to on this installation.
        # Orders this installation moved on with: kept in a merge, named in a replacement
        order_warnings = keep_newer_orders(backup_data, mode)
        # The progress counts the rows written from here on
        expect_rows(sum(section_length(backup_data, name) for name in backup_data.keys()
                        if name in RESTORED_SECTIONS and section_kind(backup_data, name) == 'list'))
        checkpoint('plan')
        plan = RestorePlan.build(backup_data, pruned=pruned)
        plan.warnings.extend(order_warnings + windows_warnings + sso_warnings)
        for warning in plan.warnings:
            logger.warning("Restore: %s", warning)
        built_with = len(plan.warnings)
        from .restore_extended import refuse_archived_shared_keys
        refuse_archived_shared_keys(backup_data, plan)

        # No file is written here: the rows commit with a new files generation and the
        # list of paths they no longer name; each node's reconciliation then follows them.
        results['mode'] = mode
        # A merge never lowers a revocation made here, of a certificate or a CA (_kept_revocation)
        self._merging = mode == 'merge'
        self._kept_revocations = []
        # SSH certificates revoked with their serial's revoked holder: audited after the commit
        self._ssh_aligned = {}

        aligned = []
        try:
            with single_transaction(results), insert_file_writes_suspended():
                # Every file the rows have now; what they still name afterwards is struck out
                generation = advance_generation() if carried else None
                if generation is not None:
                    record_removal_candidates(generation)
                from services.hsm import key_binding
                # A key two authorities held before the restore is not the restore's doing
                shared_before = set(key_binding.shared_keys())
                token_shared_before = set(key_binding.shared_token_keys())
                # Before a replacement removes certificates issued here: their serials stay given out
                SSHSerials.raise_counters(SSHSerials.session_run)
                replacement = None
                if mode == 'replace':
                    # Removed before the writes, so what they free is free
                    replacement = plan_replacement(backup_data, plan, pruned, displaced=displaced,
                                                   renamed_here=renamed_here)
                    prune_doomed_settings(replacement, plan, deferred_keys(
                        backup_data.get('configuration') if isinstance(
                            backup_data.get('configuration'), dict) else {}))
                    replacement = remove_before_writes(replacement)
                    plan.refresh()

                self._apply_all(backup_data, results, master_key, plan)

                # Sections are applied in an order that cannot satisfy every
                # reference at once, so they are resolved again now that every
                # row exists: this is where an authority finds the HSM key the
                # same restore has just created.
                checkpoint('relink')
                results['relinked'] = relink_references(backup_data, plan)
                link_restored_connectors(backup_data)
                results['repairs'] = replay_repairs(backup_data, plan)
                db.session.flush()
                # The rows written take the revocation their CA records, as the hourly pass does
                aligned = self._align_restored_revocations(plan) + self._align_kept_revocations()
                results['revoked_from_records'] = len(aligned)
                if plan.written.get('acme_client_orders'):
                    results['acme_client_orders_repaired'] = results['repairs'].get(
                        '121_acme_renewal_order_duplicates', {'reissued': 0, 'dropped': 0})
                results['settings'] += restore_setting_references(
                    backup_data.get('configuration'), plan)
                results['chain_variant_fallbacks'] = list(plan.chain_variant_fallbacks)

                if replacement is not None:
                    results.update(remove_after_writes(replacement).report())
                # On the final rows: an authority a replacement removes after the writes holds nothing
                db.session.flush()
                self._ssh_aligned.update(SSHSerials.settle_marks(SSHSerials.session_run))
                results['ssh_revoked_with_serial'] = len(self._ssh_aligned)
                aligned.extend(SSHSerials.revocation_entries(SSHSerials.session_run, self._ssh_aligned))
                SSHSerials.raise_counters(SSHSerials.session_run)
                self._settle_local_emails(backup_data)
                for key_id, held in key_binding.shared_keys().items():
                    if key_id not in shared_before:
                        raise BackupSchemaError(
                            f"Cannot restore: HSM key '{key_binding.label_of(key_id)}' would back both the "
                            f"{held[0]} and the {held[1]}. An HSM key backs one authority only; "
                            "nothing has been changed.")
                # Two key rows naming one token key are one key (refuse_same_token_key)
                for (first, second), held in key_binding.shared_token_keys().items():
                    if (first, second) not in token_shared_before:
                        raise BackupSchemaError(
                            f"Cannot restore: HSM keys '{key_binding.label_of(first)}' and "
                            f"'{key_binding.label_of(second)}' are one token key and would back both the "
                            f"{held[0]} and the {held[1]}. An HSM key backs one authority only; "
                            "nothing has been changed.")
                # Lockouts are keyed by user id and name, which either mode may hand to
                # another account; the sessions they guard are revoked after any restore
                from models.second_factor_failure import SecondFactorFailure
                db.session.execute(db.delete(SecondFactorFailure))
                # Before the warnings are reported: a keytab it cannot serve is one of them
                keytab_published = self._publish_restored_keytab(backup_data, plan)
                results['left_out'] = list(plan.left_out)
                # What applying the rows had to warn about reaches the log and the result
                for warning in dict.fromkeys(plan.warnings[built_with:]):
                    logger.warning("Restore: %s", warning)
                results['warnings'] = list(dict.fromkeys(plan.warnings))
                results['dropped_secrets'] = list(plan.dropped_fields)

                if generation is not None:
                    keep_named_paths()
                    results['files'] = {'generation': generation,
                                        'removals': removals_listed(generation)}
        except (IntegrityError, DataError) as exc:
            if isinstance(exc, DataError) and not is_value_too_long(exc):
                raise
            conflict = conflict_from_integrity_error(exc)
            logger.warning("Restore refused by the database: %s", conflict)
            raise conflict from exc

        if keytab_published:
            self._write_keytab_here()

        if aligned:
            from services.audit_service import AuditService
            for entry in aligned:
                AuditService.log_action(username='system', **entry)

        if results.get('truststore_private_keys_removed'):
            from services.audit_service import AuditService
            from utils.trust_pem import REMOVED_ACTION, removal_warning
            for entry in results['truststore_private_keys_removed']:
                AuditService.log_action(
                    action=REMOVED_ACTION, resource_type='truststore', resource_id=entry['id'],
                    resource_name=entry['name'], username='system', success=True,
                    details=removal_warning(entry['id'], entry['name'], entry['fingerprint_sha256']))

        from utils import admin_allowlist
        admin_allowlist.invalidate_cache()
        if results.get('admin_allowlist_cleared'):
            from services.audit_service import AuditService
            AuditService.log_action(
                action='admin_allowlist_update',
                resource_type='settings',
                resource_name='Admin allowlist',
                details='Admin allowlist from the restored backup cleared: it '
                        'would not admit the client that restored it',
                success=True,
            )

        # What the restore leaves behind — sessions opened before it, caches
        # holding the PKI it replaced — is the caller's to clear: this service
        # restores data, and an API route is where revoking every session and
        # asking for a restart belongs (see invalidate_after_restore).
        return results

    @staticmethod
    def _publish_restored_keytab(backup_data, plan) -> bool:
        """The profiles' section restored: the keytab file every node writes is rebuilt from
        them (A7) and the other nodes reload it, in the restore's transaction."""
        if section_kind(backup_data, 'windows_enrollment_profiles') != 'list':
            return False
        from services import cluster_commands, windows_profiles
        db.session.flush()
        try:
            windows_profiles.publish_keytab(actor='restore')
        except ValueError as exc:
            plan.warnings.append(f"windows_enrollment_profiles: the keytab is not served: {exc}")
            return False
        cluster_commands.emit(cluster_commands.RELOAD_KEYTAB)
        return True

    @staticmethod
    def _write_keytab_here() -> None:
        from services.kerberos import negotiate_auth
        try:
            negotiate_auth.write_stored_keytab()
        except (OSError, ValueError) as exc:
            logger.error("Restore: the Kerberos keytab file was not written on this node: %s", exc)

    @staticmethod
    def _align_restored_revocations(plan) -> List[Dict[str, Any]]:
        """Mark the certificate rows the restore wrote from their CA's records (the hourly
        pass's function, limited to them); returns their audit entries, logged after the commit."""
        from services.cert.issued_lookup import apply_persisted_revocations
        from services.ski_aki_backfill import _marked_entry
        ids = plan.written.get('certificates')
        if not ids:
            return []
        return [_marked_entry(row, record) for row, record in apply_persisted_revocations(ids)]

    def _align_kept_revocations(self) -> List[Dict[str, Any]]:
        """A revocation a merge kept here takes its serial's gravest record when that one is
        graver (``persisted_revocation``): a final row answers the CRL and OCSP with itself."""
        from services.cert.issued_lookup import row_persisted_revocation
        from services.ski_aki_backfill import _marked_entry
        entries = []
        for row in self.__dict__.get('_kept_revocations', ()):
            record = row_persisted_revocation(row)
            if record is not None and _revocation_key(record) < _revocation_key(row):
                row.revoked_at, row.revoke_reason = record.revoked_at, record.revoke_reason
                row.invalidity_at = record.invalidity_at or row.invalidity_at
                entries.append(_marked_entry(row, record))
        return entries

    @staticmethod
    def _check_serial_duplicates(backup_data: Dict[str, Any]) -> None:
        """Refused before any write only when the target carries the unique
        (caref, serial_number) index; a target whose unique serial index is pending accepts them."""
        from sqlalchemy import inspect
        from utils.serial_duplicates import CLEANUP, INDEX, describe, duplicates_in_rows
        if not any(ix.get('name') == INDEX for ix in inspect(db.engine).get_indexes('certificates')):
            return
        if section_kind(backup_data, 'certificates') != 'list':
            return
        # A v4 store is read row by row: the section is never loaded for this check
        rows = (backup_data.iter_rows('certificates') if isinstance(backup_data, SectionStore)
                else backup_data['certificates'])
        duplicates = duplicates_in_rows(r for r in ticking(rows) if isinstance(r, dict))
        if duplicates:
            raise BackupSchemaError(
                f"The archive holds {len(duplicates)} serial number(s) shared by certificates "
                f"of the same CA (certificate refids): {describe(duplicates)}. Nothing has been "
                f"changed. {CLEANUP} Then take a new backup.")

    @staticmethod
    def _archived_key_mismatches(backup_data: Dict[str, Any]) -> List[str]:
        """The records the archive itself flagged as key/certificate mismatches.

        Read from the metadata when it is there, and from the rows otherwise,
        so an archive written before the metadata carried the list is still
        reported rather than silently trusted.
        """
        metadata = backup_data.get('metadata') or {}
        recorded = metadata.get('key_mismatches')
        # A v4 archive always records the list, so an empty one is an answer
        if isinstance(recorded, list) and (recorded or isinstance(backup_data, SectionStore)):
            return [str(item) for item in recorded]

        found = []
        for section in ('certificate_authorities', 'certificates'):
            for row in backup_data.get(section) or []:
                if isinstance(row, dict) and row.get('_key_mismatch'):
                    found.append(f"{section}:{row.get('refid') or '?'}")
        return found

    @staticmethod
    def _sections_the_archive_replaces(backup_data):
        """Make the restore a replacement, as the documentation says it is.

        Only the sections the archive claims to describe are pruned. An
        archive says so itself: the sections it left out on purpose are listed
        in its metadata, and a section excluded at export time is one this
        archive knows nothing about, not one it says is empty. An archive of
        the authorities alone therefore replaces the authorities and leaves
        the users, the settings and the histories exactly as they are.

        One thing is refused outright: emptying the user table, which would
        leave a server nobody can sign in to.
        """
        excluded = set(
            (backup_data.get('metadata') or {}).get('excluded_sections') or [])
        sections = {name for name in backup_data.keys()
                    if name in SECTIONS and section_kind(backup_data, name) == 'list'
                    and name not in excluded}

        if 'users' in sections and not section_length(backup_data, 'users'):
            raise BackupSchemaError(
                "Refusing to restore: this archive carries no users, and a "
                "replacing restore would remove every account on this server. "
                "Nothing has been changed."
            )

        return sections

    def _apply_all(self, backup_data, results, master_key, plan):
        """Every write of a restore, inside the one transaction."""
        # Core restores
        checkpoint('core')
        self._restore_users(backup_data, results, plan)
        self._restore_cas(backup_data, results, master_key, plan)
        self._restore_certificates(backup_data, results, master_key, plan)
        self._restore_revoked_serials(backup_data, results, plan)
        self._restore_crl_number_counters(backup_data, results)
        self._restore_acme_accounts(backup_data, results)
        self._restore_acme_eab_credentials(backup_data, results)
        self._restore_settings(backup_data, results)

        # No commit here: the whole restore is one transaction, so a failure
        # in a later section cannot leave these entities applied on their own.
        db.session.flush()

        # RBAC restores
        checkpoint('rbac')
        self._restore_groups(backup_data, results, plan)
        self._restore_custom_roles(backup_data, results, plan)
        self._restore_templates(backup_data, results)
        # Settings came back before the templates: point the ACME profile
        # template bindings at the templates of the exported names, since
        # the numeric ids in the backup belong to the source instance.
        db.session.flush()
        from services.acme import profiles as acme_profiles
        results['acme_profile_bindings'] = acme_profiles.remap_template_bindings()
        self._restore_truststore(backup_data, results, plan)

        # Auth restores
        checkpoint('auth')
        self._restore_sso_providers(backup_data, results)
        self._restore_legacy_sso_identities(results, plan)
        self._restore_hsm_providers(backup_data, results, plan)
        self._restore_api_keys(backup_data, results, plan)
        self._restore_auth_certificates(backup_data, results, plan)

        # Notification restores
        checkpoint('notifications')
        self._restore_smtp_config(backup_data, results)
        self._restore_notification_config(backup_data, results)

        # Policy restores
        checkpoint('policies')
        self._restore_policies(backup_data, results, plan)
        self._restore_dns_providers(backup_data, results)
        self._restore_acme_domains(backup_data, results, plan)
        self._restore_acme_local_domains(backup_data, results, plan)

        # Extended restores
        checkpoint('extended')
        self._restore_ssh_cas(backup_data, results, master_key, plan)
        self._restore_ssh_certificates(backup_data, results, plan)
        self._restore_microsoft_cas(backup_data, results)
        self._restore_scan_profiles(backup_data, results)
        self._restore_hsm_keys(backup_data, results, plan)
        self._restore_approval_requests(backup_data, results, plan)
        self._restore_acme_client_orders(backup_data, results, plan)
        self._restore_key_recovery_requests(backup_data, results, plan)
        self._restore_https_files(backup_data, results, plan)

        # Sections the manifest carries and the hand-written restorers never
        # learned about: applied from the manifest, with every column and with
        # references resolved through the plan.
        checkpoint('generic')
        for name in GENERIC_SECTIONS:
            rows = backup_data.get(name)
            if not rows:
                continue
            if name == 'user_sso_identities':
                rows = self._identities_free_here(rows, plan)
            results[name] = apply_section(name, rows, plan)


        # Rows of another installation can name user ids this one has not handed out yet
        from services.backup import user_id_counter
        if any(_carries(backup_data, name) for name in user_id_counter.SECTIONS):
            db.session.flush()
            user_id_counter.advance_users_counter()

    def _restore_users(self, backup_data: Dict, results: Dict, plan) -> None:
        """Restore users from backup data.

        It used to write six columns: username, email, full name, role,
        active and the password hash. The manifest declares far more, the
        export has carried them since the archive was made manifest-driven,
        and this dropped every one of them -- an account came back without
        its MFA secret, without its backup codes, without the SSO identity
        that binds it to its provider, and without the custom role that gives
        it anything beyond its base rights. The restore reported a success.

        `apply_columns` writes every column the archive carries, resolves the
        references through the plan, and puts secrets back through the
        model's property, which is what re-encrypts them with this
        installation's key.
        """
        from models import User

        # An archive older than user_sso_identities carries the provider on the account row
        legacy = not _carries(backup_data, 'user_sso_identities')
        self._legacy_sso_identities = []
        for user_data in backup_data.get('users', []):
            existing = User.query.filter_by(
                username=user_data['username']).first()
            if existing is None:
                existing = User(username=user_data['username'])
                db.session.add(existing)

            # Never null out a working password with a backup that lacks one:
            # an archive written by a version that did not carry the hash
            # would otherwise lock every account out of the instance.
            carried_hash = user_data.get('password_hash')
            previous_hash = existing.password_hash

            apply_columns(existing, 'users', user_data, plan)

            if not carried_hash:
                existing.password_hash = previous_hash
            # Out of the local e-mail index until its identity rows are back (_settle_local_emails)
            existing.has_sso_identity = True
            if legacy and 'auth_source' in user_data:
                self._legacy_sso_identities.append((existing, user_data))
            results['users'] += 1

        db.session.flush()
        nested = restore_nested_webauthn(backup_data, plan)
        if nested:
            results['webauthn_credentials'] = nested

    def _settle_local_emails(self, backup_data: Dict) -> None:
        """On the final rows: the refusal of two local accounts on one e-mail, then the flag of
        every account set from its identity rows, which the local e-mail index checks."""
        from models.user import sync_sso_flags_in_session
        self._refuse_shared_local_emails(backup_data)
        sync_sso_flags_in_session(db.session)
        db.session.flush()

    @staticmethod
    def _refuse_shared_local_emails(backup_data: Dict) -> None:
        """E-mail is unique among local accounts (#136): a restored local account may not share
        one with another local account here. Said before ix_users_email_local refuses it."""
        from sqlalchemy import and_, exists
        from sqlalchemy.orm import aliased
        from models import User, UserSSOIdentity
        from .restore.conflict import RestoreConflictError

        mine, other = aliased(User), aliased(User)

        def local(account):
            # Local in SQL: the cached sso_identities predate the identity rows just restored
            return ~exists().where(UserSSOIdentity.user_id == account.id)

        names = [row['username'] for row in backup_data.get('users') or []]
        for start in range(0, len(names), 500):
            shared = (db.session.query(mine.username, other.username, mine.email)
                      .join(other, and_(other.email == mine.email, other.id != mine.id))
                      .filter(mine.username.in_(names[start:start + 500]), mine.email.isnot(None),
                              mine.email != '', local(mine), local(other))
                      .order_by(mine.id, other.id).first())
            if shared is not None:
                raise RestoreConflictError(
                    f"Refusing to restore: the local accounts {shared[0]!r} and "
                    f"{shared[1]!r} would share the e-mail {shared[2]!r}. "
                    "Nothing has been changed.")

    @staticmethod
    def _identity_holder(user_id, provider_id, external_id):
        """The other account here a provider's stable identity opens, if any."""
        from models import User, UserSSOIdentity
        if provider_id is None or not external_id:
            return None
        return (User.query.join(UserSSOIdentity, UserSSOIdentity.user_id == User.id)
                .filter(UserSSOIdentity.provider_id == provider_id,
                        UserSSOIdentity.external_id == external_id, User.id != user_id).first())

    @staticmethod
    def _skipped_identity(plan, account, provider_id, holder) -> str:
        from models.sso import SSOProvider
        provider = db.session.get(SSOProvider, provider_id)
        warning = (f"user_sso_identities: the identity of account {account!r} at provider "
                   f"{(provider.name if provider else provider_id)!r} opens the account "
                   f"{holder.username!r} here, and an identity opens one account only: it is kept "
                   f"as an orphan of an unknown IdP, which no sign-in takes back; attach a provider "
                   f"to the account to let it sign in")
        plan.warnings.append(warning)
        logger.warning("Restore: %s", warning)
        return warning

    def _identities_free_here(self, rows, plan):
        """The archive's identity rows, those whose identity opens another account here made
        orphans of an unknown IdP: an account without a row nor a password is claimable by name."""
        from models import User
        db.session.flush()
        plan.refresh(['users', 'sso_providers'])
        kept = []
        for row in rows:
            user_id = plan.resolve('user_sso_identities', row, 'user_id')
            provider_id = plan.resolve('user_sso_identities', row, 'provider_id')
            holder = self._identity_holder(user_id, provider_id, row.get('external_id'))
            if holder is None:
                kept.append(row)
                continue
            account = db.session.get(User, user_id) if user_id is not None else None
            self._skipped_identity(plan, account.username if account else None, provider_id, holder)
            kept.append({**row, 'provider_id': None, f'provider_id{REFERENCE_SUFFIX}': None,
                         'orphan_of': None})
        return kept

    def _restore_legacy_sso_identities(self, results: Dict, plan) -> None:
        """The identity rows of an archive's account rows that carry their provider (2.254, or
        3.0 before user_sso_identities), once the providers are back: the same rows an upgrade
        gives them. A provider this installation does not hold leaves an orphan of an unknown IdP."""
        from models import UserSSOIdentity
        from models.sso import SSOProvider
        from utils.sso_identity_upgrade import identity_rows

        pending = getattr(self, '_legacy_sso_identities', [])
        if not pending:
            return
        db.session.flush()
        # The archive's reference to a provider, as identity_rows reads it: its number and its
        # name, placed here by name; None only when the row names no provider at all
        here = {}
        accounts = []
        merging = getattr(self, '_merging', False)
        for user, row in pending:
            # A merge keeps the account's own rows; a replace rebuilds them from the archive
            held = UserSSOIdentity.query.filter_by(user_id=user.id)
            if merging and held.first() is not None:
                continue
            if not merging:
                held.delete(synchronize_session=False)
                # The loaded collection still lists the rows the statement deleted
                db.session.expire(user, ['sso_identities'])
            name = (row.get('sso_provider_id_ref') or {}).get('name')
            stored = None
            if row.get('sso_provider_id') is not None or name:
                stored = (row.get('sso_provider_id'), name)
                if stored not in here:
                    found = SSOProvider.query.filter_by(name=name).first() if name else None
                    here[stored] = found.id if found else None
            accounts.append((user.id, row.get('auth_source'), stored,
                             row.get('sso_external_id'), row.get('sso_orphan_of'),
                             user.password_hash, user.force_password_change))
        made = []
        names = {user.id: user.username for user, _row in pending}
        for user_id, provider_id, orphan_of, external_id in identity_rows(sorted(accounts), here):
            holder = self._identity_holder(user_id, provider_id, external_id)
            if holder is not None:
                # Kept as an orphan of an unknown IdP, as the upgrade keeps a shared identity
                self._skipped_identity(plan, names.get(user_id), provider_id, holder)
                provider_id, orphan_of = None, None
            made.append((user_id, provider_id, orphan_of, external_id))
        for user_id, provider_id, orphan_of, external_id in made:
            identity = UserSSOIdentity(user_id=user_id, provider_id=provider_id, orphan_of=orphan_of)
            identity.bind(external_id)
            db.session.add(identity)
        db.session.flush()
        self._legacy_sso_identities = []
        if made:
            results['user_sso_identities'] = results.get('user_sso_identities', 0) + len(made)

    @staticmethod
    def _apply_ca_revocation(ca, ca_data: Dict, here_revocation=None) -> None:
        """Carry the CA's revocation state back (#343): a restore that drops
        it brings a revoked CA back as active and able to sign again. A merge
        keeps ``here_revocation`` (``_kept_revocation``) over a lighter or no revocation."""
        where = f"certificate authority {ca_data.get('refid') or ca_data.get('descr')}"

        def _dt_or_none(column, val):
            return _archived_datetime(where, column, val)

        if 'revoked' not in ca_data:
            # A backup written before the fields existed says nothing about
            # revocation: the record keeps its state, and the parent's
            # revoked_serials entry keeps saying revoked (review of #347)
            return
        ca.revoked = bool(ca_data.get('revoked', False))
        ca.revoked_at = _dt_or_none('revoked_at', ca_data.get('revoked_at'))
        ca.revoke_reason = ca_data.get('revoke_reason')
        ca.invalidity_at = _dt_or_none('invalidity_at', ca_data.get('invalidity_at'))
        if here_revocation is not None and (not ca.revoked or _revocation_key(ca) > _revocation_key(here_revocation)):
            for field, value in vars(here_revocation).items():
                setattr(ca, field, value)

    @staticmethod
    def _apply_ca_fields(ca, ca_data: Dict) -> None:
        """Apply the exported settings a restore used to drop: validity dates,
        origin, CDP/OCSP/AIA/CPS publication settings and the offline state.
        Fields absent from an older backup leave the record as it is."""
        where = f"certificate authority {ca_data.get('refid') or ca_data.get('descr')}"

        if 'valid_from' in ca_data:
            ca.valid_from = _archived_datetime(where, 'valid_from',
                                               ca_data.get('valid_from'))
        if 'valid_to' in ca_data:
            ca.valid_to = _archived_datetime(where, 'valid_to',
                                             ca_data.get('valid_to'))
        for column in ('imported_from', 'created_by', 'cdp_enabled', 'cdp_url', 'ocsp_enabled',
                       'ocsp_url', 'aia_ca_issuers_enabled', 'aia_ca_issuers_url', 'cps_enabled',
                       'cps_uri', 'cps_oid', 'path_length'):
            if column in ca_data and hasattr(ca, column):
                setattr(ca, column, ca_data.get(column))
        if ca_data.get('signature_scheme') in SIGNATURE_SCHEMES:
            ca.signature_scheme = ca_data['signature_scheme']
        if is_valid_profile(ca_data.get('compliance_profile')):
            ca.compliance_profile = ca_data['compliance_profile']
        for column, setter in (('cdp_urls', 'set_cdp_urls'), ('ocsp_urls', 'set_ocsp_urls'),
                               ('aia_ca_issuers_urls', 'set_aia_urls')):
            if column in ca_data and isinstance(ca_data.get(column), list):
                getattr(ca, setter)(ca_data[column])
        # An archive from before the upgrade brings back what its migration repaired
        for column in ('cdp_url', 'ocsp_url', 'aia_ca_issuers_url'):
            setattr(ca, column, strip_port_zero_from_stored(getattr(ca, column)))
        if 'offline' in ca_data:
            # An offline CA restored as online would hold a passphrase
            # protected key it cannot use and could neither take offline nor
            # bring back (review of #347)
            ca.offline = bool(ca_data.get('offline', False))
            ca.offline_mode = ca_data.get('offline_mode')
            ca.offline_reason = ca_data.get('offline_reason')

    def _restore_revoked_serials(self, backup_data: Dict, results: Dict,
                                 plan=None) -> None:
        """Restore the persistent revocation records (#343).

        The certificate a record revokes is resolved where the row is
        written. It used to be set to None and left to `relink_references` at
        the very end of the restore: the column tolerates it, so the repair
        did arrive, but a revocation record with no certificate beside it is
        the one row of the database nobody wants half-written, and the repair
        is not reached when a later section refuses the archive.
        """
        from models.revoked_serial import RevokedSerial
        from utils.serial_format import canonical_serial
        from .restore.plan import RestorePlan
        from .restore_extended import reindex_reference_targets

        plan = plan if plan is not None else RestorePlan.build(backup_data)
        reindex_reference_targets('revoked_serials', plan)

        results.setdefault('revoked_serials', 0)
        results.setdefault('revoked_serials_skipped', 0)
        # The archive's own leftovers of a lifted hold are not suspensions; nothing here is touched
        from .restore.repairs import archived_lifted_holds
        lifted = archived_lifted_holds(backup_data)
        results['lifted_holds_skipped'] = len(lifted)
        if lifted:
            logger.info("Restore: %d hold record(s) an older release left behind a lifted hold "
                        "not restored", len(lifted))
        # A record whose CA is neither in the database nor in the backup
        # would fail the foreign key on PostgreSQL and abort the whole restore
        known = {ca.refid for ca in CA.query.with_entities(CA.refid).all()}
        known.update(c.get('refid') for c in backup_data.get('certificate_authorities', []) if c.get('refid'))
        for position, rs_data in enumerate(backup_data.get('revoked_serials', [])):
            tick(1)
            if position in lifted:
                continue
            caref = rs_data.get('caref')
            # An older archive holds any spelling: matched and written in the stored one
            serial = canonical_serial(rs_data.get('serial_number'))
            if not caref or not serial:
                # Both columns are NOT NULL on the model, so no export writes
                # such a row: it used to be dropped without a word, which for
                # a revocation record means a certificate silently coming back
                # valid.
                raise BackupSchemaError(
                    f"Invalid backup: revoked serial {position} names "
                    "neither a serial number nor the authority that revoked "
                    "it. Nothing has been changed.")
            if caref not in known:
                # The one tolerated skip of this section: the record names a
                # CA that is neither in this database nor in the archive, so
                # there is nothing here for it to revoke. Writing it would
                # break the foreign key on PostgreSQL; the serial and the CA
                # are named so the skip can be read in the log.
                logger.warning(f"Revoked serial {serial} skipped: CA {caref} is unknown")
                results['revoked_serials_skipped'] += 1
                continue
            # A refusal names the serial as the archive spells it
            where = f"revoked serial {rs_data.get('serial_number')} of CA {caref}"
            here = RevokedSerial.query.filter_by(
                caref=caref, serial_number=serial
            ).order_by(RevokedSerial.id).all()
            taken = plan.rank('revoked_serials', (caref, str(serial)), rs_data, [r.id for r in here])
            existing = next((r for r in here if r.id == taken), None)
            valid_to = _archived_datetime(
                where, 'valid_to', rs_data.get('valid_to')) or utc_now()
            revoked_at = _archived_datetime(
                where, 'revoked_at', rs_data.get('revoked_at'))
            invalidity_at = _archived_datetime(
                where, 'invalidity_at', rs_data.get('invalidity_at'))
            certificate_id = plan.resolve('revoked_serials', rs_data,
                                          'certificate_id')
            if existing:
                archived = SimpleNamespace(revoke_reason=rs_data.get('revoke_reason'),
                                           revoked_at=revoked_at or existing.revoked_at,
                                           invalidity_at=invalidity_at)
                # A merge keeps the graver of the two, between equals the earlier
                if not (getattr(self, '_merging', False)
                        and _revocation_key(existing) <= _revocation_key(archived)):
                    existing.revoked_at = archived.revoked_at
                    existing.revoke_reason = archived.revoke_reason
                    existing.invalidity_at = archived.invalidity_at
                existing.valid_to = valid_to
                existing.certificate_id = certificate_id
                # An archive older than the column says nothing of the key
                existing.public_key_sha256 = rs_data.get('public_key_sha256') or existing.public_key_sha256
                plan.place('revoked_serials', rs_data, existing)
            else:
                existing = RevokedSerial(
                    caref=caref,
                    serial_number=serial,
                    revoked_at=revoked_at or utc_now(),
                    revoke_reason=rs_data.get('revoke_reason'),
                    invalidity_at=invalidity_at,
                    valid_to=valid_to,
                    certificate_id=certificate_id,
                    public_key_sha256=rs_data.get('public_key_sha256'),
                )
                db.session.add(existing)
                plan.place('revoked_serials', rs_data, existing)
            results['revoked_serials'] += 1

    def _restore_crl_number_counters(self, backup_data: Dict, results: Dict) -> None:
        """Each issuer's CRL number, never lowered: the higher of here and the archive."""
        from models.crl import CRLNumberCounter
        for position, row in enumerate(backup_data.get('crl_number_counters') or []):
            tick(1)   # every row announced by expect_rows is counted, written or left out
            issuer_key, number = row.get('issuer_key'), row.get('last_number')
            if (not isinstance(issuer_key, str) or not isinstance(number, int)
                    or isinstance(number, bool)):
                raise BackupSchemaError(
                    f"Invalid backup: CRL number counter {position} is malformed. "
                    "Nothing has been changed.")
            counter = CRLNumberCounter.query.filter_by(issuer_key=issuer_key).first()
            if counter is None:
                db.session.add(CRLNumberCounter(issuer_key=issuer_key, last_number=number))
            elif number > (counter.last_number or 0):
                counter.last_number = number
            results['crl_number_counters'] += 1

    def _restore_cas(self, backup_data: Dict, results: Dict, master_key: bytes,
                     plan=None) -> None:
        """Restore certificate authorities from backup data.

        A CA that already exists here is written exactly like one being
        created: every column the archive carries goes back. Restoring a
        handful of fields onto an existing row left the CA holding its own
        subject, serial, url_slug, path length, name constraints and CRL
        cadence while claiming to be the archived one -- an instance matching
        neither the archive nor its previous state.
        """
        # Called directly (tests, legacy paths) without the restore's plan:
        # build one, so references still land on the row the archive names
        # rather than on whatever holds that number here.
        plan = plan if plan is not None else RestorePlan.build(backup_data)
        from .restore_extended import _refuse_a_taken_key
        taken = {}

        for ca_data in backup_data.get('certificate_authorities', []):
            ca = CA.query.filter_by(refid=ca_data['refid']).first()

            # Decrypt private key if encrypted
            prv_pem = None
            if ca_data.get('private_key_pem_encrypted'):
                prv_pem = self._decrypt_archived_key(
                    ca_data['private_key_pem_encrypted'], master_key, f"CA {ca_data['refid']}")
            prv_b64 = base64.b64encode(prv_pem.encode()).decode() if prv_pem else None
            if prv_b64:
                from security.encryption import encrypt_private_key
                prv_b64 = encrypt_private_key(prv_b64)

            # Read before apply_columns writes the archive's revocation columns
            here_revocation = _kept_revocation(self, ca)
            if ca is None:
                # descr and crt are NOT NULL; both are overwritten below
                ca = CA(refid=ca_data['refid'], descr=ca_data.get('descr'), crt='')
                db.session.add(ca)

            # Every column the manifest declares, references resolved through
            # the plan. The key material and the PEMs are left out (the
            # manifest marks them `handled`): only this method holds the
            # archive's master key, so only it can put them back.
            apply_columns(ca, 'certificate_authorities', ca_data, plan)

            # '' is the sentinel for a CA awaiting its external certificate
            # (migration 079) and the column is NOT NULL: writing None there
            # aborted the whole restore
            ca.crt = (
                base64.b64encode(ca_data['certificate_pem'].encode()).decode()
                if ca_data.get('certificate_pem') else ''
            )
            ca.csr = ca_data.get('csr_pem') or ca.csr
            ca.prv = prv_b64
            ca.serial_number = ca_data.get('serial_number') or ca.serial_number
            ca.ski = ca_data.get('ski') or ca.ski
            self._apply_ca_fields(ca, ca_data)
            self._apply_ca_revocation(ca, ca_data, here_revocation)
            _refuse_a_taken_key(ca, taken)
            results['cas'] += 1

    def _restore_certificates(self, backup_data: Dict, results: Dict, master_key: bytes,
                              plan=None) -> None:
        """Restore certificates from backup data.

        As for CAs, an existing row is written exactly like a new one. The
        restore used to touch five fields on a certificate it found here, so
        its subject, serial, SANs, source, template and renewal history stayed
        as they were while the restore reported success.
        """
        plan = plan if plan is not None else RestorePlan.build(backup_data)

        written = []
        kept_revocations = self.__dict__.setdefault('_kept_revocations', [])
        for cert_data in backup_data.get('certificates', []):
            cert = Certificate.query.filter_by(refid=cert_data['refid']).first()

            # Decrypt private key if encrypted
            prv_pem = None
            if cert_data.get('private_key_pem_encrypted'):
                prv_pem = self._decrypt_archived_key(
                    cert_data['private_key_pem_encrypted'], master_key,
                    f"certificate {cert_data['refid']}")

            prv_b64 = None
            if prv_pem:
                prv_b64 = base64.b64encode(prv_pem.encode()).decode()
                from security.encryption import encrypt_private_key
                prv_b64 = encrypt_private_key(prv_b64)

            here_state = None if cert is None else SimpleNamespace(
                revoked=cert.revoked, revoked_at=cert.revoked_at,
                revoke_reason=cert.revoke_reason, invalidity_at=cert.invalidity_at)
            if cert is None:
                # descr is NOT NULL; overwritten by apply_columns below
                cert = Certificate(refid=cert_data['refid'],
                                   descr=cert_data.get('descr'))
                db.session.add(cert)

            # Every column of the section, references resolved through the
            # plan; the PEMs and the key are `handled` and set right after.
            if not apply_columns(cert, 'certificates', cert_data, plan):
                continue    # left out, and listed: nothing more is written for it

            cert.crt = (
                base64.b64encode(cert_data['certificate_pem'].encode()).decode()
                if cert_data.get('certificate_pem') else None
            )
            if 'csr_pem' in cert_data:
                # Absent from a dict written before the column was carried:
                # only an archive that says something about the CSR replaces it
                cert.csr = (
                    base64.b64encode(cert_data['csr_pem'].encode()).decode()
                    if cert_data['csr_pem'] else None
                )
            if prv_b64:
                cert.prv = prv_b64
            where = f"certificate {cert_data.get('refid')}"
            here_revocation = _kept_revocation(self, here_state)
            cert.revoked = bool(cert_data.get('revoked', False))
            cert.revoked_at = _archived_datetime(where, 'revoked_at',
                                                 cert_data.get('revoked_at'))
            cert.revoke_reason = cert_data.get('revoke_reason')
            if 'invalidity_at' in cert_data:
                cert.invalidity_at = _archived_datetime(
                    where, 'invalidity_at', cert_data.get('invalidity_at'))
            if here_revocation is not None and (not cert.revoked or _revocation_key(cert) > _revocation_key(here_revocation)):
                for field, value in vars(here_revocation).items():
                    setattr(cert, field, value)
                kept_revocations.append(cert)
            cert.archived = bool(cert_data.get('archived', False))
            written.append(cert)
            results['certificates'] += 1
            if len(written) % PEM_RELEASE_ROWS == 0:
                _release_pems(written[-PEM_RELEASE_ROWS:])
        db.session.flush()
        _release_pems(written[-(len(written) % PEM_RELEASE_ROWS or PEM_RELEASE_ROWS):])
        plan.written.setdefault('certificates', set()).update(cert.id for cert in written)

    def _restore_acme_accounts(self, backup_data: Dict, results: Dict) -> None:
        """Restore ACME accounts from backup data (RFC 8555)"""
        for acme_data in backup_data.get('acme_accounts', []):
            tick(1)   # every row announced by expect_rows is counted, written or left out
            account_id = acme_data.get('account_id')
            jwk_thumbprint = acme_data.get('jwk_thumbprint')
            if not account_id or not jwk_thumbprint or not acme_data.get('jwk'):
                continue
            existing = AcmeAccount.query.filter_by(account_id=account_id).first()
            target = existing
            if existing:
                existing.jwk = acme_data['jwk']
                existing.jwk_thumbprint = jwk_thumbprint
                existing.contact = acme_data.get('contact')
                existing.status = acme_data.get('status', 'valid')
                existing.terms_of_service_agreed = acme_data.get('terms_of_service_agreed', False)
                existing.external_account_binding = acme_data.get('external_account_binding')
            else:
                new_acme = AcmeAccount(
                    account_id=account_id,
                    jwk=acme_data['jwk'],
                    jwk_thumbprint=jwk_thumbprint,
                    contact=acme_data.get('contact'),
                    status=acme_data.get('status', 'valid'),
                    terms_of_service_agreed=acme_data.get('terms_of_service_agreed', False),
                    external_account_binding=acme_data.get('external_account_binding'),
                )
                db.session.add(new_acme)
                target = new_acme
            _archived_timestamps(target, f"ACME account {account_id}", acme_data)
            results['acme_accounts'] += 1

    def _restore_acme_eab_credentials(self, backup_data: Dict, results: Dict) -> None:
        """Restore ACME EAB credentials from backup data (RFC 8555).

        The whole section used to sit inside one `except Exception`, so a
        single unreadable row, or a model this build does not have, dropped
        every external account binding the archive carried: the ACME clients
        bound to them would simply stop being able to register, and the
        restore reported success. Nothing is caught here any more.
        """
        from models.acme_models import AcmeEabCredential

        results.setdefault('acme_eab_credentials', 0)
        for eab in backup_data.get('acme_eab_credentials', []):
            tick(1)   # every row announced by expect_rows is counted, written or left out
            kid = eab.get('kid')
            if not kid or not eab.get('hmac_key_b64'):
                continue
            where = f"ACME EAB credential {kid}"
            expires_at = _archived_datetime(where, 'expires_at', eab.get('expires_at'))
            used_at = _archived_datetime(where, 'used_at', eab.get('used_at'))
            revoked_at = _archived_datetime(where, 'revoked_at', eab.get('revoked_at'))
            existing = AcmeEabCredential.query.filter_by(kid=kid).first()
            target = existing
            if existing:
                existing.hmac_key_b64 = eab['hmac_key_b64']
                existing.label = eab.get('label')
                existing.notes = eab.get('notes')
                existing.status = eab.get('status', 'active')
                existing.used_at = used_at
                existing.used_by_account_id = eab.get('used_by_account_id')
                existing.revoked_at = revoked_at
                existing.revoked_by_user_id = eab.get('revoked_by_user_id')
                existing.expires_at = expires_at
            else:
                new_eab = AcmeEabCredential(
                    kid=kid,
                    hmac_key_b64=eab['hmac_key_b64'],
                    label=eab.get('label'),
                    notes=eab.get('notes'),
                    created_by_user_id=eab.get('created_by_user_id'),
                    expires_at=expires_at,
                    used_at=used_at,
                    used_by_account_id=eab.get('used_by_account_id'),
                    revoked_at=revoked_at,
                    revoked_by_user_id=eab.get('revoked_by_user_id'),
                    status=eab.get('status', 'active'),
                )
                db.session.add(new_eab)
                target = new_eab
            # The archive holds the column's JSON text; NULL means every domain,
            # so dropping it would lift the credential's limits.
            if 'allowed_domains' in eab:
                limits = eab['allowed_domains']
                if limits is not None and not isinstance(limits, str):
                    raise BackupSchemaError(f"{where}: allowed_domains is not JSON text")
                target._allowed_domains = limits
            _archived_timestamps(target, where, eab)
            results['acme_eab_credentials'] += 1

    def _restore_settings(self, backup_data: Dict, results: Dict) -> None:
        """Restore system settings from backup data"""
        from models import SystemConfig
        configuration = backup_data.get('configuration', {})
        # Handle legacy backups where configuration might be a list instead of dict
        if isinstance(configuration, list):
            config_data = {}
        else:
            config_data = configuration.get('settings', {})
        from utils import admin_allowlist
        # Settings naming a row by number wait for that row: see restore/setting_refs.py
        deferred = deferred_keys(configuration if isinstance(configuration, dict) else {})
        for key, value in config_data.items():
            if installation.is_local_setting(key) or key in deferred:
                continue    # this database's own, never the source's
            if key == admin_allowlist.CONFIG_KEY and admin_allowlist.restored_value_locks_out(value):
                if admin_allowlist.disabled_by_env():
                    logger.warning(
                        "Restore: the archived admin allowlist (%s) would not admit "
                        "this restore's client; kept because UCM_ADMIN_ALLOWLIST_DISABLE is set", value)
                else:
                    logger.warning(
                        "Restore: the archived admin allowlist (%s) would not admit "
                        "this restore's client, so it was cleared", value)
                    results['admin_allowlist_cleared'] = True
                    value = ''
            existing = SystemConfig.query.filter_by(key=key).first()
            if existing:
                existing.value = value
            else:
                new_config = SystemConfig(key=key, value=value)
                db.session.add(new_config)
            results['settings'] += 1

        # Settings the archive carries in the clear because they are stored
        # encrypted: written back encrypted with this installation's key.
        results['encrypted_settings'] = restore_encrypted_settings(
            configuration if isinstance(configuration, dict) else {},
            (configuration or {}).get('encrypted_settings') or [], skip=deferred)
