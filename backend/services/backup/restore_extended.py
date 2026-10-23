"""Extended restore methods mixin for BackupService.

Every section here is applied through `apply_columns`, from the manifest the
export was written from. The hand-written assignments it replaces had the
same two faults throughout:

* they wrote a hand-picked list of columns, and only onto rows they were
  creating -- an SSH authority, a Microsoft connector, a scan profile or an
  HSM key this installation already had was counted as restored and left
  exactly as it was, and `microsoft_cas.winrm_password` was on no list at
  all, so the WinRM credential was lost at every restore;
* they wrote the source's own numeric ids into foreign keys --
  `ssh_certificates.ssh_ca_id`, `hsm_keys.provider_id`,
  `ssh_cas.owner_group_id` -- and counted on `relink_references`, at the very
  end of the restore, to point them at the right row. SQLite enforces no
  foreign key, so the repair arrived in time and nobody was any the wiser;
  PostgreSQL refuses the insert as it happens, and the whole restore with it.

References are resolved where the row is written instead, against a plan
re-indexed for the sections this one points at (`reindex_reference_targets`).
"""
import uuid
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import inspect as sa_inspect

from models import db
from config.settings import Config
from utils.datetime_utils import to_naive_utc

from .errors import BackupSchemaError
from .export_generic import REFERENCE_SUFFIX, load_model
from .manifest import SECTIONS
from .restore.apply import apply_columns
from .restore.plan import RestorePlan, RestoreValidationError

logger = logging.getLogger(__name__)


def _missing_support(section_name: str, rows, feature: str) -> None:
    """Say which section an installation without `feature` cannot take.

    The import of an optional model is the one failure here that is not a
    loss: the rows describe a feature this build does not have, so there is
    nothing on this installation for them to be applied to. It used to
    `break` without a word, which is the same outcome without the sentence
    that lets an administrator see it happened.
    """
    logger.warning(
        "Restore: this installation has no %s support; the %d row(s) of "
        "section '%s' in the archive were not applied",
        feature, len(rows), section_name)


def reindex_reference_targets(section_name: str, plan: RestorePlan) -> None:
    """Re-read the identities of the sections this one points at.

    The plan is built before the restore writes anything, which is the point:
    nothing is created until what the restore will do has been decided. But a
    section points at rows this same restore created a few sections earlier --
    an SSH certificate at its authority, an ACME domain at its DNS provider, a
    policy at its CA -- and against the original index those references
    resolved to nothing at all.

    So the index is rebuilt here, once per section rather than once per row,
    exactly as `apply_section` does it for the manifest-driven sections. It
    happens before the first row of the section is added to the session: a
    query with a half-built row pending would autoflush it into a constraint
    violation.
    """
    references = SECTIONS[section_name].references
    if not references:
        return
    db.session.flush()
    plan.refresh(sorted(set(references.values())))


def _required(where: str, row: Dict[str, Any], column: str) -> Any:
    """A column the row cannot be written without, or a refusal naming it.

    Raised as a schema error rather than left to the KeyError it used to be:
    the routes return this message to the administrator, and "SSH certificate
    3 names no authority" is what they need, not "Restore failed".
    """
    value = row.get(column)
    if value in (None, ''):
        raise BackupSchemaError(
            f"Invalid backup: {where} has no {column}, which it cannot be "
            "restored without. Nothing has been changed.")
    return value


def _timestamp(where: str, column: str, value: Any,
               required: bool = False, reason: str = 'part of what identifies '
               'it') -> Optional[datetime]:
    """The instant the archive recorded, or a refusal.

    A date that could not be parsed used to become None, so an approval
    request came back without the creation date that identifies it and with
    no trace of the value that was dropped. A date the column cannot do
    without is refused here rather than by the driver, which names a table
    and leaves the operator to guess which of its rows was at fault.
    """
    if value in (None, ''):
        if required:
            raise RestoreValidationError(
                f"Invalid backup: {where} has no {column}, which is "
                f"{reason}; nothing has been changed")
        return None
    if isinstance(value, datetime):
        return to_naive_utc(value)
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError) as exc:
        raise RestoreValidationError(
            f"Invalid backup: {where} holds {value!r} as its {column}, which "
            "is not a date; nothing has been changed") from exc
    return to_naive_utc(parsed)


def _reference(where: str, section_name: str, row: Dict[str, Any], column: str,
               plan: RestorePlan) -> Optional[Any]:
    """The id this installation holds for the row a reference points at.

    The archive carries the source's numeric id and, beside it, the identity
    of the row it pointed at; only the identity means anything here. The plan
    answers from the index it took before the first write, so a row this very
    restore has just created — the certificate an approval was waiting for,
    the user who asked for it — is looked up again on the session.

    A reference the archive carries and this installation cannot place stops
    the restore: writing the source's number would attach the request to
    whichever row happens to hold it here, and dropping it would turn an
    approved request into one that looks like it is still waiting.
    """
    if row.get(column) is None:
        return None                      # there was no link to carry
    resolved = plan.resolve(section_name, row, column)
    if resolved is None:
        resolved = _target_id(section_name, row, column)
    if resolved is None:
        identity = row.get(f'{column}{REFERENCE_SUFFIX}')
        raise RestoreValidationError(
            f"Invalid backup: {where} points at a "
            f"{SECTIONS[section_name].references[column]} row this "
            f"installation does not have "
            f"({identity or 'the archive carries no identity for it'}); "
            "nothing has been changed")
    return resolved


def _target_id(section_name: str, row: Dict[str, Any], column: str) -> Optional[Any]:
    """The referenced row's id, as the session sees it now.

    The plan's index is a snapshot taken before the restore wrote anything;
    this reads the same identity against the rows the restore has since
    created, which is the difference between a full archive restoring onto a
    fresh installation and one that refuses because its own users are not
    there yet.
    """
    identity = row.get(f'{column}{REFERENCE_SUFFIX}')
    if not identity:
        return None
    section = SECTIONS[SECTIONS[section_name].references[column]]
    values = {field: identity.get(field) for field in section.identity}
    if any(value is None for value in values.values()):
        # An identity this version cannot read in full matches nothing here;
        # looking it up would be a search for a row holding NULL.
        return None
    model = load_model(section)
    found = model.query.filter_by(**values).first()
    if found is None:
        return None
    primary = sa_inspect(model).primary_key
    if len(primary) != 1:
        return None
    return getattr(found, primary[0].key)


def _existing_row(section_name: str, identity: Dict[str, Any]):
    """The row here that an archived row is, by the identity the manifest declares.

    Looked up on the session rather than in the plan's index: for an approval
    request the index holds the source's certificate id and an unparsed date,
    neither of which is what this restore computes, and in both sections it
    was taken before the first write, so a row an earlier row of the same
    archive created would not be in it.

    A row whose identity is empty is no row in particular: it is created
    rather than matched against every other row that has none either. The
    plan has already said so, as a warning, when it read the archive.
    """
    section = SECTIONS[section_name]
    if tuple(identity) != section.identity:
        raise RestoreValidationError(
            f"Section '{section_name}' is identified by "
            f"{', '.join(section.identity)}, not by "
            f"{', '.join(identity)}")
    if all(value in (None, '') for value in identity.values()):
        return None
    return load_model(section).query.filter_by(**identity).first()


class RestoreExtendedMixin:
    def _restore_ssh_cas(self, backup_data: Dict, results: Dict, master_key: bytes,
                         plan: Optional[RestorePlan] = None) -> None:
        """Restore SSH certificate authorities from backup data.

        Every column the archive carries is applied through `apply_columns`,
        to an authority already here exactly as to one being created. An
        existing refid used to be passed over entirely: the restore counted
        it and wrote nothing, so the authority kept the target's own public
        key, principals, TTLs and serial counter while the archive said
        otherwise. What the hand-written list did write, it wrote with the
        source's `owner_group_id` -- the group that number happens to name
        here, or none at all -- and left `relink_references` to repair it at
        the very end, which PostgreSQL does not wait for.

        The private key stays by hand: the manifest marks it `handled`
        because only this method holds the archive's master key, so only it
        can put the material back under *this* installation's key. A key that
        cannot be decrypted stops the restore -- it used to be a warning, and
        the authority was created with an empty private key and committed, so
        the restore reported success and left an SSH CA that signs nothing.
        """
        results.setdefault('ssh_cas', 0)
        rows = backup_data.get('ssh_cas', [])
        if not rows:
            return
        # Only the SSH model is conditional here. Key encryption is not: a
        # missing security.encryption must stop the restore, never let it
        # write the SSH CA key in cleartext.
        from security.encryption import encrypt_private_key
        try:
            from models.ssh import SSHCertificateAuthority
        except ImportError:
            _missing_support('ssh_cas', rows, 'SSH')
            return

        plan = plan if plan is not None else RestorePlan.build(backup_data)
        reindex_reference_targets('ssh_cas', plan)

        for sca_data in rows:
            refid = sca_data.get('refid')
            sca = _existing_row('ssh_cas', {'refid': refid})
            if sca is None:
                # refid, descr, ca_type, public_key, private_key, key_type,
                # fingerprint and serial_counter are NOT NULL; all but the
                # private key are overwritten by apply_columns below.
                sca = SSHCertificateAuthority(
                    refid=refid or str(uuid.uuid4()),
                    descr=sca_data.get('descr') or 'Imported SSH CA',
                    ca_type=sca_data.get('ca_type') or 'user',
                    key_type=sca_data.get('key_type') or 'ed25519',
                    public_key=sca_data.get('public_key') or '',
                    private_key='',
                    fingerprint=sca_data.get('fingerprint') or '',
                    serial_counter=sca_data.get('serial_counter') or 0,
                )
                db.session.add(sca)

            apply_columns(sca, 'ssh_cas', sca_data, plan)
            if 'allow_any_principal' not in sca_data:
                # An older archive: an empty list meant any principal then
                sca.allow_any_principal = not sca.get_allowed_principals()

            encrypted = sca_data.get('private_key_pem_encrypted')
            prv = sca_data.get('_private_key_plaintext')
            if encrypted:
                try:
                    prv = self._decrypt_private_key(encrypted, master_key)
                except Exception as exc:
                    raise BackupSchemaError(
                        f"Invalid backup: the private key of SSH CA "
                        f"{refid or sca_data.get('descr') or '(unnamed)'} could "
                        "not be decrypted. Restoring it would create an "
                        "authority that can sign nothing; nothing has been "
                        "changed."
                    ) from exc
            if prv:
                sca.private_key = encrypt_private_key(prv)
            results['ssh_cas'] += 1

        # One flush for the section, not a commit per row: the restore is one
        # transaction, and a row that cannot be written must take it down
        # rather than become the warning it used to be.
        db.session.flush()

    def _restore_ssh_certificates(self, backup_data: Dict, results: Dict,
                                  plan: Optional[RestorePlan] = None) -> None:
        """Restore SSH certificates from backup data.

        The row is the manifest's -- every column of it, and the authority it
        names resolved to the id that authority has *here*. The number the
        archive carries is the source's: written as it stood, it attached the
        certificate to whichever authority holds that number on this
        installation, and where none did, PostgreSQL refused the insert and
        took the whole restore with it while SQLite waited for
        `relink_references` to repair it.

        A row that cannot be written is still the restore's failure, not a
        line in a log: a missing authority or an unreadable date used to drop
        the certificate and let the restore report the ones that worked.
        """
        results.setdefault('ssh_certificates', 0)
        rows = backup_data.get('ssh_certificates', [])
        if not rows:
            return
        try:
            from models.ssh import SSHCertificate
        except ImportError:
            _missing_support('ssh_certificates', rows, 'SSH')
            return

        plan = plan if plan is not None else RestorePlan.build(backup_data)
        reindex_reference_targets('ssh_certificates', plan)

        for position, sc_data in enumerate(rows):
            where = f"SSH certificate {sc_data.get('refid') or position}"
            _required(where, sc_data, 'ssh_ca_id')
            authority_id = _reference(where, 'ssh_certificates', sc_data,
                                      'ssh_ca_id', plan)

            # The manifest identifies a certificate by its serial and its
            # authority, and the authority is the one resolved just above:
            # matching on the archive's number would look for the authority
            # the source used.
            sc = _existing_row('ssh_certificates',
                               {'serial': sc_data.get('serial'),
                                'ssh_ca_id': authority_id})
            if sc is None:
                # refid, ssh_ca_id, cert_type, key_id, public_key,
                # certificate, principals, serial, valid_from, valid_to,
                # key_type and fingerprint are NOT NULL; apply_columns
                # overwrites every one of them, ssh_ca_id with the same
                # resolved id.
                sc = SSHCertificate(
                    refid=sc_data.get('refid') or str(uuid.uuid4()),
                    ssh_ca_id=authority_id,
                    cert_type=sc_data.get('cert_type') or 'user',
                    key_id=sc_data.get('key_id') or '',
                    public_key=sc_data.get('public_key') or '',
                    certificate=sc_data.get('certificate') or '',
                    principals=sc_data.get('principals') or '[]',
                    serial=sc_data.get('serial') or 0,
                    valid_from=_timestamp(where, 'valid_from',
                                          sc_data.get('valid_from'),
                                          required=True,
                                          reason='a column it cannot be '
                                                 'written without'),
                    valid_to=_timestamp(where, 'valid_to',
                                        sc_data.get('valid_to'),
                                        required=True,
                                        reason='a column it cannot be '
                                               'written without'),
                    key_type=sc_data.get('key_type') or 'ed25519',
                    fingerprint=sc_data.get('fingerprint') or '',
                )
                db.session.add(sc)

            apply_columns(sc, 'ssh_certificates', sc_data, plan)
            results['ssh_certificates'] += 1

        db.session.flush()

    def _restore_microsoft_cas(self, backup_data: Dict, results: Dict,
                               plan: Optional[RestorePlan] = None) -> None:
        """Restore Microsoft certificate authorities from backup data.

        Sixteen columns were written by hand out of a model that holds
        thirty-eight, and only on a connector this installation did not
        already have. Two of the missing ones are the reason this is not a
        cosmetic difference: `winrm_password` was on no list at all, so the
        credential of the administration channel was lost at every restore,
        and the WinRM settings around it (host, port, transport, TLS
        verification) came back as the model's defaults rather than as the
        archive's.

        `password` and `winrm_password` are assigned by their manifest name,
        which is the model's property: it re-encrypts them with this
        installation's database key, where writing the column underneath
        would have left them readable.

        A connector the archive carries and this restore cannot write is a CA
        that will not answer on the restored instance; it fails the restore
        instead of disappearing into a warning.
        """
        results.setdefault('microsoft_cas', 0)
        rows = backup_data.get('microsoft_cas', [])
        if not rows:
            return
        try:
            from models.msca import MicrosoftCA
        except ImportError:
            _missing_support('microsoft_cas', rows, 'Microsoft CA')
            return

        plan = plan if plan is not None else RestorePlan()

        for position, msca_data in enumerate(rows):
            where = f"Microsoft CA {msca_data.get('name') or position}"
            name = _required(where, msca_data, 'name')
            msca = _existing_row('microsoft_cas', {'name': name})
            if msca is None:
                # name, server and auth_method are NOT NULL; all three are
                # overwritten by apply_columns.
                msca = MicrosoftCA(
                    name=name,
                    server=msca_data.get('server') or '',
                    auth_method=msca_data.get('auth_method') or 'ntlm',
                )
                db.session.add(msca)

            apply_columns(msca, 'microsoft_cas', msca_data, plan)
            results['microsoft_cas'] += 1

        db.session.flush()

    def _restore_scan_profiles(self, backup_data: Dict, results: Dict,
                               plan: Optional[RestorePlan] = None) -> None:
        """Restore scan profiles from backup data.

        Applied from the manifest, and to a profile already here as to a new
        one: an existing name was skipped, so a profile came back with the
        targets, ports and schedule the target held rather than the archive's,
        and the columns added to the model after the hand-written list --
        `last_scan_at`, `next_scan_at`, `updated_at` -- reached no restore at
        all.

        A profile the archive carries and this restore drops is a discovery
        scan that will never run again on the restored instance, so it fails
        the restore rather than being logged and passed over.
        """
        results.setdefault('scan_profiles', 0)
        rows = backup_data.get('scan_profiles', [])
        if not rows:
            return
        try:
            from models.discovered_certificate import ScanProfile
        except ImportError:
            _missing_support('scan_profiles', rows, 'certificate discovery')
            return

        plan = plan if plan is not None else RestorePlan()

        for position, sp_data in enumerate(rows):
            where = f"scan profile {sp_data.get('name') or position}"
            name = _required(where, sp_data, 'name')
            sp = _existing_row('scan_profiles', {'name': name})
            if sp is None:
                sp = ScanProfile(name=name)      # NOT NULL
                db.session.add(sp)
            apply_columns(sp, 'scan_profiles', sp_data, plan)
            results['scan_profiles'] += 1

        db.session.flush()

    def _restore_hsm_keys(self, backup_data: Dict, results: Dict,
                          plan: Optional[RestorePlan] = None) -> None:
        """Restore HSM keys from backup data.

        A key that does not come back is a CA that cannot sign: the
        authorities are relinked to these rows afterwards, so losing one here
        would restore an HSM-backed CA with no key to reach for. The failure
        stops the restore instead of being logged.

        The provider is resolved to the id it has *here*, both to find the
        row the archive describes -- the manifest identifies a key by
        (provider, identifier), and the archive's provider is the source's
        number -- and to write it: `provider_id` is NOT NULL and carries a
        foreign key, so the source's number was an insert PostgreSQL refused
        outright and SQLite only survived because `relink_references` came
        along at the end and repaired it.
        """
        results.setdefault('hsm_keys', 0)
        rows = backup_data.get('hsm_keys', [])
        if not rows:
            return
        try:
            from models.hsm import HsmKey
        except ImportError:
            _missing_support('hsm_keys', rows, 'HSM')
            return

        plan = plan if plan is not None else RestorePlan.build(backup_data)
        reindex_reference_targets('hsm_keys', plan)

        for position, k_data in enumerate(rows):
            where = f"HSM key {k_data.get('key_identifier') or position}"
            _required(where, k_data, 'provider_id')
            provider_id = _reference(where, 'hsm_keys', k_data, 'provider_id', plan)

            hk = _existing_row('hsm_keys',
                               {'provider_id': provider_id,
                                'key_identifier': k_data.get('key_identifier')})
            if hk is None:
                # provider_id, key_identifier, label, algorithm, key_type and
                # purpose are NOT NULL; apply_columns overwrites them all.
                hk = HsmKey(
                    provider_id=provider_id,
                    key_identifier=k_data.get('key_identifier'),
                    label=k_data.get('label') or '',
                    algorithm=k_data.get('algorithm') or '',
                    key_type=k_data.get('key_type') or '',
                    purpose=k_data.get('purpose') or '',
                )
                db.session.add(hk)

            apply_columns(hk, 'hsm_keys', k_data, plan)
            results['hsm_keys'] += 1

        db.session.flush()

    def _restore_approval_requests(self, backup_data: Dict, results: Dict,
                                   plan: Optional[RestorePlan] = None) -> None:
        """Restore approval requests, once and with their dates.

        Every row used to be created unconditionally, so restoring the same
        archive twice left two copies of every pending request, each still
        waiting on the same certificate. A request is now the row the
        manifest says it is -- the certificate it is about, as that
        certificate is numbered *here*, and the instant it was created -- so a
        second restore updates what the first one wrote instead of adding to
        it. The creation date is carried back rather than replaced by the
        moment of the restore, which is also what makes the identity hold.

        The row itself goes through `apply_columns`, to one that already
        exists exactly as to a new one: a restore that left half the fields of
        an existing request as they were would match neither the archive nor
        what was here. `created_at` is handed over already parsed, since it is
        the value the identity was looked up with.
        """
        from models.policy import ApprovalRequest

        results.setdefault('approval_requests', 0)
        rows = backup_data.get('approval_requests', [])
        if not rows:
            return

        plan = plan if plan is not None else RestorePlan.build(backup_data)
        reindex_reference_targets('approval_requests', plan)

        for position, ar_data in enumerate(rows):
            where = f"approval request {position}"
            created_at = _timestamp(where, 'created_at', ar_data.get('created_at'),
                                    required=True)
            certificate_id = _reference(where, 'approval_requests', ar_data,
                                        'certificate_id', plan)
            # None only when the archive names none (a request the renewal
            # scheduler queued); a requester this installation lacks stops it
            requester_id = _reference(where, 'approval_requests', ar_data,
                                      'requester_id', plan)

            request = _existing_row('approval_requests',
                                    {'certificate_id': certificate_id,
                                     'created_at': created_at})
            if request is None:
                # request_type is NOT NULL; apply_columns overwrites it and requester_id
                request = ApprovalRequest(
                    request_type=ar_data.get('request_type') or 'certificate',
                    requester_id=requester_id)
                db.session.add(request)

            apply_columns(request, 'approval_requests',
                          dict(ar_data, created_at=created_at), plan)
            results['approval_requests'] += 1

        db.session.flush()

    def _restore_acme_client_orders(self, backup_data: Dict, results: Dict,
                                    plan: Optional[RestorePlan] = None) -> None:
        """Restore the orders UCM placed with an external ACME CA, once.

        An order is the one the CA knows under that URL, so restoring an
        archive twice updates the order it already put back rather than
        placing a second row for the same upstream order.

        Every column comes from the manifest now: the hand-written list was
        missing the CSR the order was placed with, the certificate it renews,
        its expiry and its renewal history, so a restored order was one the
        renewal could not carry on from.
        """
        from models.acme_models import AcmeClientOrder

        results.setdefault('acme_client_orders', 0)
        rows = backup_data.get('acme_client_orders', [])
        if not rows:
            return

        plan = plan if plan is not None else RestorePlan.build(backup_data)
        reindex_reference_targets('acme_client_orders', plan)

        for o_data in rows:
            order = _existing_row('acme_client_orders',
                                  {'order_url': o_data.get('order_url')})
            if order is None:
                # domains, challenge_type, environment, key_source and status
                # are NOT NULL; all of them are overwritten by apply_columns.
                order = AcmeClientOrder(domains=o_data.get('domains') or '[]')
                db.session.add(order)

            # `certificate_id` is a column like any other here: the manifest
            # carries no identity for the issued certificate, so there is
            # nothing to resolve it against and the archive's own number is
            # written, exactly as this restore has always written it.
            apply_columns(order, 'acme_client_orders', o_data, plan)
            results['acme_client_orders'] += 1

        db.session.flush()

    def _restore_https_files(self, backup_data: Dict, results: Dict,
                             staged=None) -> None:
        """Stage the HTTPS server certificate and key.

        Nothing is written where the server reads it until the database
        transaction has committed: the pair used to be written in the middle
        of the restore, so a failure afterwards left the server presenting a
        certificate from an archive that was never applied. Failures are no
        longer swallowed either — a restore that cannot place the key it was
        asked to restore has not restored it.
        """
        https_data = backup_data.get('https_server', {})
        if not https_data:
            return
        if staged is None:
            raise RuntimeError("HTTPS files must be staged, not written directly")

        if https_data.get('cert_pem'):
            staged.stage(Config.HTTPS_CERT_PATH,
                         https_data['cert_pem'].encode(), mode=0o644)
            results['https_server'] += 1
        if https_data.get('key_pem'):
            staged.stage(Config.HTTPS_KEY_PATH,
                         https_data['key_pem'].encode(), mode=0o600)
            results['https_server'] += 1
