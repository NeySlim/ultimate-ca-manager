"""
Core restore methods mixin for BackupService
"""
import json
import hashlib
import base64
import logging
from datetime import datetime
from typing import Any, Dict, List

from models import db, CA, Certificate
from utils.datetime_utils import utc_now
from models.acme_models import AcmeAccount
from config.settings import Config
from services.file_regen_service import mirror_private_key

from .errors import BackupSchemaError
from .restore import RestorePlan, single_transaction
from .restore.files import StagedFiles
from .manifest import SECTIONS
from .restore.apply import apply_columns, apply_section, relink_references
from .restore.replace import replace_sections
from .restore.settings import restore_encrypted_settings

logger = logging.getLogger(__name__)


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


# Sections this restore path knows how to apply. The export carries more
# than this (the manifest is ahead of the restore), so what is not applied is
# reported rather than passed over: an archive holding webhook endpoints and
# deployment targets must not restore as a success that silently dropped them.
# Sections the manifest-driven applier puts back, in an order where a
# section comes after everything it points at: a membership needs its user and
# its group, a binding needs its target and its certificate.
GENERIC_SECTIONS = (
    'role_permissions',
    'group_members',
    'webauthn_credentials',
    'ad_connector',
    'webhook_endpoints',
    'deploy_targets',
    'deploy_bindings',
    'crl_deploy_bindings',
    'intune_apps',
    'scep_profiles',
    'ca_template_pins',
    'acme_client_accounts',
    'key_recovery_requests',
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

RESTORED_SECTIONS = set(GENERIC_SECTIONS) | {
    'users', 'certificate_authorities', 'certificates', 'revoked_serials',
    'acme_accounts', 'acme_eab_credentials', 'configuration', 'groups',
    'custom_roles', 'certificate_templates', 'trusted_certificates',
    'sso_providers', 'hsm_providers', 'hsm_keys', 'api_keys', 'smtp_config',
    'notification_config', 'certificate_policies', 'auth_certificates',
    'dns_providers', 'acme_domains', 'acme_local_domains', 'ssh_cas',
    'ssh_certificates', 'microsoft_cas', 'msca_requests', 'scan_profiles',
    'scan_runs', 'discovered_certificates', 'approval_requests',
    'scep_requests', 'acme_client_orders', 'audit_logs', 'https_server',
}


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

        self._check_section_counts(backup_data, metadata.get('sections'))
        self._check_section_digests(backup_data, metadata.get('section_digests'))

    @staticmethod
    def _check_section_digests(backup_data: Dict[str, Any], digests: Any) -> None:
        """Compare each section against the digest the archive recorded.

        The payload checksum says the archive is damaged; this says which
        section, which is what decides whether a restore is worth attempting.
        """
        if digests is None:
            return
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
            value = backup_data[name]
            if not isinstance(value, (list, dict)):
                raise BackupSchemaError(
                    f"Invalid backup format: section '{name}' is neither a list nor "
                    "an object")
            if len(value) != expected:
                raise BackupSchemaError(
                    f"Incomplete backup: section '{name}' holds {len(value)} entries, "
                    f"{expected} were written"
                )

    def restore_backup(self, backup_bytes: bytes, password: str, *, mode: str = 'replace') -> Dict[str, Any]:
        """
        Restore from encrypted backup. Auto-detects format v1 (legacy) or v2.

        Args:
            backup_bytes: Encrypted backup file content
            password: Decryption password

        Returns:
            Dict with restore results
        """
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

        # Everything the payload claims about itself is checked here, before
        # the first write: a schema this version cannot read, or a section
        # holding fewer rows than the archive says it holds, must not be
        # discovered halfway through a restore.
        self._check_payload_schema(backup_data)

        # An archive of metadata alone restores nothing. Announcing it as a
        # success made the caller revoke every session and ask for a restart
        # over a file that changed not one row.
        carried = sorted(
            name for name in SECTIONS
            if backup_data.get(name)
        )

        # Named before anything is written, so the answer can say what this
        # version will not put back even though the archive carries it.
        not_restored = sorted(
            name for name, value in backup_data.items()
            if name not in ('metadata', 'checksum')
            and name not in RESTORED_SECTIONS
            and value
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
            'sections_not_restored': not_restored,
            'sections_carried': carried,
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
        plan = RestorePlan.build(backup_data)
        for warning in plan.warnings:
            logger.warning("Restore: %s", warning)

        # Files are written to a staging directory during the transaction and
        # published once it has committed, so the database and the files on
        # disk can never disagree about whether the restore happened.
        if mode not in ('replace', 'merge'):
            raise BackupSchemaError(
                f"Unknown restore mode {mode!r}: use 'replace' (the archive "
                "becomes the instance) or 'merge' (the archive is added to it)")
        results['mode'] = mode

        staged = StagedFiles()
        try:
            with single_transaction():
                self._apply_all(backup_data, results, master_key, plan, staged)

                # Sections are applied in an order that cannot satisfy every
                # reference at once, so they are resolved again now that every
                # row exists: this is where an authority finds the HSM key the
                # same restore has just created.
                results['relinked'] = relink_references(backup_data, plan)

                if mode == 'replace':
                    results['removed'] = self._remove_what_the_archive_omits(
                        backup_data, plan)

                # Published inside the transaction, so a file that cannot be
                # placed rolls the database back with it. The window that
                # remains is the commit itself, and it is compensated below.
                staged.publish()
        except Exception:
            # The commit is the last thing the block does: if it is what
            # failed, the files are already in place and describe a restore
            # that did not happen.
            staged.unpublish()
            staged.discard()
            raise
        finally:
            staged.discard()

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
    def _archived_key_mismatches(backup_data: Dict[str, Any]) -> List[str]:
        """The records the archive itself flagged as key/certificate mismatches.

        Read from the metadata when it is there, and from the rows otherwise,
        so an archive written before the metadata carried the list is still
        reported rather than silently trusted.
        """
        metadata = backup_data.get('metadata') or {}
        recorded = metadata.get('key_mismatches')
        if isinstance(recorded, list) and recorded:
            return [str(item) for item in recorded]

        found = []
        for section in ('certificate_authorities', 'certificates'):
            for row in backup_data.get(section) or []:
                if isinstance(row, dict) and row.get('_key_mismatch'):
                    found.append(f"{section}:{row.get('refid') or '?'}")
        return found

    @staticmethod
    def _remove_what_the_archive_omits(backup_data, plan):
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
        sections = {name for name, value in backup_data.items()
                    if name in SECTIONS and isinstance(value, list)
                    and name not in excluded}

        if 'users' in sections and not backup_data.get('users'):
            raise BackupSchemaError(
                "Refusing to restore: this archive carries no users, and a "
                "replacing restore would remove every account on this server. "
                "Nothing has been changed."
            )

        return replace_sections(backup_data, plan, sections)

    def _apply_all(self, backup_data, results, master_key, plan, staged):
        """Every write of a restore, inside the one transaction."""
        # Core restores
        self._restore_users(backup_data, results, plan)
        self._restore_cas(backup_data, results, master_key, plan)
        self._restore_certificates(backup_data, results, master_key, plan)
        self._restore_revoked_serials(backup_data, results, plan)
        self._restore_acme_accounts(backup_data, results)
        self._restore_acme_eab_credentials(backup_data, results)
        self._restore_settings(backup_data, results)

        # No commit here: the whole restore is one transaction, so a failure
        # in a later section cannot leave these entities applied on their own.
        db.session.flush()

        # Regenerate CA/cert files on disk
        self._regenerate_files(staged)

        # RBAC restores
        self._restore_groups(backup_data, results)
        self._restore_custom_roles(backup_data, results, plan)
        self._restore_templates(backup_data, results)
        # Settings came back before the templates: point the ACME profile
        # template bindings at the templates of the exported names, since
        # the numeric ids in the backup belong to the source instance.
        db.session.flush()
        from services.acme import profiles as acme_profiles
        results['acme_profile_bindings'] = acme_profiles.remap_template_bindings()
        self._restore_truststore(backup_data, results)

        # Auth restores
        self._restore_sso_providers(backup_data, results)
        self._restore_hsm_providers(backup_data, results, plan)
        self._restore_api_keys(backup_data, results, plan)
        self._restore_auth_certificates(backup_data, results, plan)

        # Notification restores
        self._restore_smtp_config(backup_data, results)
        self._restore_notification_config(backup_data, results)

        # Policy restores
        self._restore_policies(backup_data, results, plan)
        self._restore_dns_providers(backup_data, results)
        self._restore_acme_domains(backup_data, results, plan)
        self._restore_acme_local_domains(backup_data, results, plan)

        # Extended restores
        self._restore_ssh_cas(backup_data, results, master_key, plan)
        self._restore_ssh_certificates(backup_data, results, plan)
        self._restore_microsoft_cas(backup_data, results)
        self._restore_scan_profiles(backup_data, results)
        self._restore_hsm_keys(backup_data, results, plan)
        self._restore_approval_requests(backup_data, results, plan)
        self._restore_acme_client_orders(backup_data, results, plan)
        self._restore_https_files(backup_data, results, staged)

        # Sections the manifest carries and the hand-written restorers never
        # learned about: applied from the manifest, with every column and with
        # references resolved through the plan.
        for name in GENERIC_SECTIONS:
            rows = backup_data.get(name)
            if not rows:
                continue
            results[name] = apply_section(name, rows, plan)

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
            results['users'] += 1

    @staticmethod
    def _apply_ca_revocation(ca, ca_data: Dict) -> None:
        """Carry the CA's revocation state back (#343): a restore that drops
        it brings a revoked CA back as active and able to sign again."""
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
        for column, setter in (('cdp_urls', 'set_cdp_urls'), ('ocsp_urls', 'set_ocsp_urls'),
                               ('aia_ca_issuers_urls', 'set_aia_urls')):
            if column in ca_data and isinstance(ca_data.get(column), list):
                getattr(ca, setter)(ca_data[column])
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
        from .restore.plan import RestorePlan
        from .restore_extended import reindex_reference_targets

        plan = plan if plan is not None else RestorePlan.build(backup_data)
        reindex_reference_targets('revoked_serials', plan)

        results.setdefault('revoked_serials', 0)
        results.setdefault('revoked_serials_skipped', 0)
        # A record whose CA is neither in the database nor in the backup
        # would fail the foreign key on PostgreSQL and abort the whole restore
        known = {ca.refid for ca in CA.query.with_entities(CA.refid).all()}
        known.update(c.get('refid') for c in backup_data.get('certificate_authorities', []) if c.get('refid'))
        for position, rs_data in enumerate(backup_data.get('revoked_serials', [])):
            caref = rs_data.get('caref')
            serial = rs_data.get('serial_number')
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
            where = f"revoked serial {serial} of CA {caref}"
            existing = RevokedSerial.query.filter_by(
                caref=caref, serial_number=serial
            ).first()
            valid_to = _archived_datetime(
                where, 'valid_to', rs_data.get('valid_to')) or utc_now()
            revoked_at = _archived_datetime(
                where, 'revoked_at', rs_data.get('revoked_at'))
            invalidity_at = _archived_datetime(
                where, 'invalidity_at', rs_data.get('invalidity_at'))
            certificate_id = plan.resolve('revoked_serials', rs_data,
                                          'certificate_id')
            if existing:
                existing.revoked_at = revoked_at or existing.revoked_at
                existing.revoke_reason = rs_data.get('revoke_reason')
                existing.invalidity_at = invalidity_at
                existing.valid_to = valid_to
                existing.certificate_id = certificate_id
            else:
                db.session.add(RevokedSerial(
                    caref=caref,
                    serial_number=serial,
                    revoked_at=revoked_at or utc_now(),
                    revoke_reason=rs_data.get('revoke_reason'),
                    invalidity_at=invalidity_at,
                    valid_to=valid_to,
                    certificate_id=certificate_id,
                ))
            results['revoked_serials'] += 1

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

        for ca_data in backup_data.get('certificate_authorities', []):
            ca = CA.query.filter_by(refid=ca_data['refid']).first()

            # Decrypt private key if encrypted
            prv_pem = None
            if ca_data.get('private_key_pem_encrypted'):
                prv_pem = self._decrypt_private_key(
                    ca_data['private_key_pem_encrypted'],
                    master_key
                )
            prv_b64 = base64.b64encode(prv_pem.encode()).decode() if prv_pem else None
            if prv_b64:
                from security.encryption import encrypt_private_key
                prv_b64 = encrypt_private_key(prv_b64)

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
            self._apply_ca_revocation(ca, ca_data)
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

        for cert_data in backup_data.get('certificates', []):
            cert = Certificate.query.filter_by(refid=cert_data['refid']).first()

            # Decrypt private key if encrypted
            prv_pem = None
            if cert_data.get('private_key_pem_encrypted'):
                prv_pem = self._decrypt_private_key(
                    cert_data['private_key_pem_encrypted'],
                    master_key
                )

            prv_b64 = None
            if prv_pem:
                prv_b64 = base64.b64encode(prv_pem.encode()).decode()
                from security.encryption import encrypt_private_key
                prv_b64 = encrypt_private_key(prv_b64)

            if cert is None:
                # descr is NOT NULL; overwritten by apply_columns below
                cert = Certificate(refid=cert_data['refid'],
                                   descr=cert_data.get('descr'))
                db.session.add(cert)

            # Every column of the section, references resolved through the
            # plan; the PEMs and the key are `handled` and set right after.
            apply_columns(cert, 'certificates', cert_data, plan)

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
            cert.revoked = bool(cert_data.get('revoked', False))
            cert.revoked_at = _archived_datetime(where, 'revoked_at',
                                                 cert_data.get('revoked_at'))
            cert.revoke_reason = cert_data.get('revoke_reason')
            if 'invalidity_at' in cert_data:
                cert.invalidity_at = _archived_datetime(
                    where, 'invalidity_at', cert_data.get('invalidity_at'))
            cert.archived = bool(cert_data.get('archived', False))
            results['certificates'] += 1

    def _restore_acme_accounts(self, backup_data: Dict, results: Dict) -> None:
        """Restore ACME accounts from backup data (RFC 8555)"""
        for acme_data in backup_data.get('acme_accounts', []):
            account_id = acme_data.get('account_id')
            jwk_thumbprint = acme_data.get('jwk_thumbprint')
            if not account_id or not jwk_thumbprint or not acme_data.get('jwk'):
                continue
            existing = AcmeAccount.query.filter_by(account_id=account_id).first()
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
        for key, value in config_data.items():
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
            (configuration or {}).get('encrypted_settings') or [])

    def _regenerate_files(self, staged) -> None:
        """Write the files that materialise the restored rows on disk.

        Every failure here used to be `pass`: a restore that could not write
        a single file still reported success. Two kinds are distinguished,
        because they do not mean the same thing.

        A write that fails — no space left, a read-only directory — stops the
        restore. It runs inside the transaction, so the rows go back with it
        and the instance stays as it was, which is the only outcome that
        matches what the caller is told.

        The certificate and CSR files are staged rather than written in
        place, and published with the rest once the transaction has
        committed: written directly, a restore that failed afterwards left
        every certificate file holding the archive's content while the rows
        had gone back to what they were. The key mirrors are the exception
        and stay a direct write, because mirroring is also a *removal* when
        database encryption is on, which staging does not express; each one
        is atomic on its own (see ``mirror_private_key``).

        Material that cannot be decoded is a warning naming the row, and the
        restore goes on. This walks every authority and certificate in the
        database, not only the ones the archive carried: a row whose stored
        key predates this installation's KEY_ENCRYPTION_KEY was already
        unreadable before the restore, so nothing is lost by not mirroring
        it, and refusing would make an instance holding one such row
        impossible to restore at all. What the archive itself brought cannot
        land here: it was just encoded by this process, a few lines above.
        """
        from utils.file_naming import ca_cert_path, ca_key_path, cert_cert_path, cert_key_path, cert_csr_path
        from utils.key_codec import load_pem_bytes

        for ca in CA.query.all():
            if ca.crt:
                try:
                    cert_pem = base64.b64decode(ca.crt)
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "Restore: the stored certificate of CA %s could not be "
                        "decoded (%s); its file was not written", ca.id, exc)
                else:
                    Config.CA_DIR.mkdir(parents=True, exist_ok=True)
                    staged.stage(ca_cert_path(ca), cert_pem, mode=0o644)
            if ca.prv:
                try:
                    prv_pem = load_pem_bytes(ca.prv, context=f"CA {ca.id}")
                except ValueError as exc:
                    logger.warning(
                        "Restore: the stored key of CA %s could not be read "
                        "(%s); it was not mirrored on disk", ca.id, exc)
                else:
                    mirror_private_key(
                        ca_key_path(ca), prv_pem, context=f"restored CA {ca.id}"
                    )

        for cert in Certificate.query.all():
            if cert.crt:
                try:
                    cert_pem_bytes = base64.b64decode(cert.crt)
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "Restore: the stored certificate %s could not be "
                        "decoded (%s); its file was not written", cert.id, exc)
                else:
                    Config.CERT_DIR.mkdir(parents=True, exist_ok=True)
                    staged.stage(cert_cert_path(cert), cert_pem_bytes,
                                 mode=0o644)
            if cert.csr:
                try:
                    csr_data = cert.csr
                    if csr_data.startswith('-----BEGIN'):
                        csr_bytes = csr_data.encode('utf-8')
                    else:
                        csr_bytes = base64.b64decode(csr_data)
                except (ValueError, TypeError, AttributeError) as exc:
                    logger.warning(
                        "Restore: the stored CSR of certificate %s could not "
                        "be decoded (%s); its file was not written",
                        cert.id, exc)
                else:
                    staged.stage(cert_csr_path(cert), csr_bytes, mode=0o644)
            if cert.prv:
                try:
                    prv_pem_bytes = load_pem_bytes(cert.prv, context=f"certificate {cert.id}")
                except ValueError as exc:
                    logger.warning(
                        "Restore: the stored key of certificate %s could not "
                        "be read (%s); it was not mirrored on disk",
                        cert.id, exc)
                else:
                    mirror_private_key(
                        cert_key_path(cert),
                        prv_pem_bytes,
                        context=f"restored certificate {cert.id}",
                    )
