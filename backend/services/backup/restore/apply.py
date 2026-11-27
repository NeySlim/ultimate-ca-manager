"""Applying a section, from the same manifest the export was written from.

The old restore set a hand-picked subset of fields, and only on rows it
decided to create: restoring over an existing certificate left its subject,
serial, validity and SANs as they were, so a restore could leave an instance
that matched neither the archive nor its previous state. Here every column the
archive carries is applied, to a row that already exists exactly as to a row
being created, and the references are the ones the plan resolved rather than
the source's numeric ids.

Secrets go back through the model's property, not the column: the property is
what re-encrypts them with *this* installation's key, which is what makes an
archive restorable somewhere else at all.
"""
import base64
import json
import logging
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.types import (
    Boolean,
    Date,
    DateTime,
    Integer,
    JSON,
    LargeBinary,
    Numeric,
)

from models import db
from utils.nul_text import NUL, escape_nul

from ..export_generic import CHAIN_VARIANT_FINGERPRINT, REFERENCE_SUFFIX, load_model
from ..manifest import SECTIONS
from . import audit_ids
from .kept_states import held_here, put_back
from .plan import RestorePlan, RestoreValidationError, row_label
from .transaction import tick
from .windows_profiles import IDENTITY as _PROFILE_IDENTITY, PROFILES as _PROFILES, restored_identity

logger = logging.getLogger(__name__)


# Column objects and mapped attribute names per model, built once: a restore
# walks thousands of rows and the mapper does not change between them.
_MAPPING_CACHE: Dict[Any, Any] = {}


def _mapping_of(model):
    """(column by name, mapped attribute name by column name) for a model."""
    cached = _MAPPING_CACHE.get(model)
    if cached is None:
        mapper = sa_inspect(model)
        columns = {column.key: column for column in mapper.columns}
        attribute_of = {}
        for prop in mapper.column_attrs:
            for column in prop.columns:
                attribute_of[column.key] = prop.key
        cached = (columns, attribute_of)
        _MAPPING_CACHE[model] = cached
    return cached


class UnplaceableLegacyRow(RestoreValidationError):
    """A required link an older archive names by its source number alone."""


def apply_columns(instance, section_name: str, row: Dict[str, Any],
                  plan: RestorePlan, archived: Optional[Dict[str, Any]] = None) -> bool:
    """Put every column the archive carries for this row onto `instance`.

    This is the whole of "restoring a row", and it is deliberately the same
    call for a row being created and for one that already exists: the restore
    used to set a hand-picked subset of fields on an existing certificate or
    CA, so its subject, serial, SANs, template or CRL cadence stayed at
    whatever the target happened to hold.

    The columns the manifest marks `handled` are left out: a dedicated
    restorer owns them because it is the one holding the archive's master key
    (the PEMs and the private key). Everything else comes from here.

    Returns False when the row is left out (`UnplaceableLegacyRow`): a new
    row leaves the session again, and `plan.left_out` says why. `archived`
    is the archive's row when `row` is a copy of it: the plan records the
    row written for that one (`RestorePlan.place`).
    """
    tick(1)
    section = SECTIONS[section_name]
    columns, attribute_of = _mapping_of(type(instance))
    applied = _apply_or_leave_out(section_name, section, instance, row, columns,
                                  attribute_of, plan)
    if applied:
        plan.place(section_name, row if archived is None else archived, instance)
    return applied


def _apply_or_leave_out(section_name, section, instance, row, columns, attribute_of, plan) -> bool:
    state = sa_inspect(instance)
    new = state.transient or state.pending
    held = None if new else held_here(section_name, instance, plan.merging)
    try:
        _apply_row(section_name, section, instance, row, columns, attribute_of, plan, new)
        put_back(section_name, instance, held, plan)
    except UnplaceableLegacyRow as left_out:
        if new and state.persistent:
            db.session.delete(instance)
        elif new and state.pending:
            db.session.expunge(instance)
        plan.left_out.append(str(left_out))
        logger.warning("Restore: %s", left_out)
        return False
    return True


def apply_section(section_name: str, rows: List[Dict[str, Any]],
                  plan: RestorePlan) -> int:
    """Create or update every row of a section. Returns the number applied.

    Raises rather than skipping: a row this version cannot apply is a restore
    that would be announced as complete while missing part of the archive.
    """
    section = SECTIONS[section_name]
    model = load_model(section)
    mapper = sa_inspect(model)
    columns, attribute_of = _mapping_of(model)

    primary = [column.key for column in mapper.primary_key]
    if len(primary) != 1:
        raise RestoreValidationError(
            f"Section '{section_name}' has a composite primary key; this "
            "version cannot apply it")

    # The plan was built before anything was written, which is the point: no
    # row is created until what the restore will do is decided. But a section
    # can point at a row this same restore has just created a few sections
    # earlier, and against the original index that reference resolved to
    # nothing. Where the column requires a value the insert then failed and
    # took the whole restore with it -- a membership, a role permission, a
    # WebAuthn credential, a deployment binding, a template pin, a key
    # recovery request: six sections that made a restore onto a fresh
    # installation impossible.
    #
    # Only the sections this one points at are rebuilt, and only once per
    # section rather than once per row: re-indexing the whole archive for
    # every row would turn a restore into a walk over the database.
    if section.references:
        db.session.flush()
        plan.refresh(sorted(set(section.references.values())))

    # An audit entry's seal covers its id: a replacement writes each back under its own
    keep_ids = section_name == audit_ids.SECTION and plan.keep_audit_ids
    if keep_ids:
        audit_ids.hold_appends()
    applied = 0
    for row in rows:
        tick(1)
        target_id = row['id'] if keep_ids else plan.existing_id(section_name, row)
        instance = db.session.get(model, target_id) if target_id is not None else None
        created = instance is None
        if created:
            instance = model(id=row['id']) if keep_ids else model()
            db.session.add(instance)

        if _apply_or_leave_out(section_name, section, instance, row, columns,
                               attribute_of, plan):
            plan.place(section_name, row, instance)
            applied += 1
            if created and section_name == audit_ids.SECTION and not keep_ids:
                plan.audit_new += 1

    db.session.flush()
    return applied


# A column added after an archive was written: the archive's silence means the
# value its author's version implied, not the model's default of today.
LEGACY_DEFAULTS = {
    'deploy_bindings': {'include_root': True},   # every fullchain carried the root before 089
}


def legacy_defaults(section_name, row, plan=None) -> dict:
    """The values an older archive implied for the columns it does not name."""
    defaults = {
        column: value
        for column, value in LEGACY_DEFAULTS.get(section_name, {}).items()
        if column not in row
    }
    # Before migration 091 the reload command belonged to the SSH target.
    # Restores happen after migrations, so an old archive's binding rows never
    # pass through 091. Preserve the old behaviour by copying the archived
    # target command into each binding that does not carry its own command.
    if section_name == 'deploy_bindings' and 'reload_command' not in row and plan:
        target_identity = row.get(f'target_id{REFERENCE_SUFFIX}') or {}
        target_id = row.get('target_id')
        for target in plan.rows.get('deploy_targets') or []:
            same_identity = (target_identity and all(
                target.get(key) == value for key, value in target_identity.items()))
            same_legacy_id = (not target_identity and target.get('id') == target_id)
            if same_identity or same_legacy_id:
                defaults['reload_command'] = target.get('reload_command')
                break
    # Before migration 092 the Entra app registration sat on the profile. An
    # archive of that shape gets an app row, shared by the profiles that
    # carried the same tenant and client, and the frozen columns stay empty.
    if section_name == 'scep_profiles' and 'intune_app_id' not in row:
        defaults.update(_legacy_intune_app(row))
    return defaults


def _legacy_intune_app(row) -> dict:
    from models.scep import IntuneApp
    from utils.encryption import encrypt_value
    tenant = (row.get('intune_tenant_id') or '').strip()
    client = (row.get('intune_client_id') or '').strip()
    secret = row.get('intune_client_secret') or ''
    cleared = {'intune_tenant_id': None, 'intune_client_id': None,
               'intune_client_secret': None}
    if not (tenant and client and secret):
        return cleared
    # The registration with these very credentials; a different secret for the
    # same tenant and client keeps a registration of its own, nothing is lost
    app = next((candidate for candidate in
                IntuneApp.query.filter_by(tenant_id=tenant, client_id=client).all()
                if candidate.decrypted_secret() == secret), None)
    if app is None:
        wanted = (row.get('name') or 'Intune')[:100]
        name, n = wanted, 2
        while IntuneApp.query.filter_by(name=name).first() is not None:
            suffix = f' ({n})'
            name, n = wanted[:100 - len(suffix)] + suffix, n + 1
        app = IntuneApp(name=name, tenant_id=tenant, client_id=client,
                        client_secret=encrypt_value(secret))
        db.session.add(app)
        db.session.flush()
    return {'intune_app_id': app.id, **cleared}


def _apply_row(section_name, section, instance, row, columns, attribute_of, plan, new=True):
    for name, value in row.items():
        if name.startswith('_') or name.endswith(REFERENCE_SUFFIX):
            continue          # internal marker, or the identity of a reference
        if name in section.handled:
            continue          # the dedicated restorer owns this column
        if name == 'id':
            continue          # the target keeps its own key
        if section_name == _PROFILES and name in _PROFILE_IDENTITY:
            continue          # restored_identity decides, below
        column = columns.get(name)
        if column is None and name in section.secrets and isinstance(
                getattr(type(instance), name, None), property):
            # A property over a column of another name (`_auth_token`): its setter encrypts
            setattr(instance, name, _secret_as_stored(
                section, name, value, label=_row_label(section_name, section, row),
                dropped=plan.dropped_fields))
            continue
        if column is None:
            continue          # a column this version does not have

        if name in section.references:
            if not new and f'{name}{REFERENCE_SUFFIX}' not in row and row.get(name) is not None:
                continue      # a link from before identities: the row keeps its own
            resolved = plan.resolve(section_name, row, name)
            if resolved is None and row.get(name) is not None:
                if _unplaceable_reference(section_name, section, name, row, column,
                                          instance, attribute_of.get(name, name)):
                    continue      # an existing row keeps the link it has
            setattr(instance, attribute_of.get(name, name), resolved)
            continue

        if name in section.secrets:
            setattr(instance, name, _secret_as_stored(
                section, name, value, label=_row_label(section_name, section, row),
                dropped=plan.dropped_fields))
            continue

        if section_name == 'deploy_bindings' and name == 'chain_variant':
            value = _restored_chain_variant(row, value, plan)

        setattr(instance, attribute_of.get(name, name),
                _coerce(value, column, f"{section_name}.{name}"))
    for column, value in legacy_defaults(section_name, row, plan).items():
        setattr(instance, attribute_of.get(column, column), value)
    if section_name == _PROFILES:
        for column, value in restored_identity(instance, row, new=new, replacing=_PROFILES in plan.pruned,
                                               warnings=plan.warnings).items():
            setattr(instance, column, value)


def _restored_chain_variant(row, value, plan):
    """`cross:<id>` names a row renumbered on restore: found again by fingerprint, else `auto`."""
    if not str(value or '').startswith('cross:'):
        return value
    from models import db
    from models.ca_cross_certificate import CACrossCertificate
    fingerprint = row.get(CHAIN_VARIANT_FINGERPRINT)
    target = None
    if fingerprint:
        # The binding being built is not complete yet: it must not be flushed here.
        with db.session.no_autoflush:
            target = CACrossCertificate.query.filter_by(fingerprint_sha256=fingerprint).first()
    if target is None:
        logger.warning("Deploy binding chain_variant %s: its cross-certificate is not on this "
                       "installation, the binding falls back to 'auto'", value)
        plan.chain_variant_fallbacks.append(_binding_label(row))
        return 'auto'
    return f'cross:{target.id}'


def _binding_label(row) -> str:
    """A deploy binding by the names an operator finds it under here: certificate and target."""
    from models import Certificate
    target = (row.get(f'target_id{REFERENCE_SUFFIX}') or {}).get('name') or '?'
    refid = (row.get(f'certificate_id{REFERENCE_SUFFIX}') or {}).get('refid')
    with db.session.no_autoflush:
        cert = Certificate.query.filter_by(refid=refid).first() if refid else None
    return f"certificate '{cert.descr if cert else refid or '?'}' on target '{target}'"


_row_label = row_label


def _unplaceable_reference(section_name, section, name, row, column,
                           instance=None, attribute=None) -> bool:
    """A reference the archive carries and this installation cannot place.

    Left alone, a column that requires a value took `None` and the insert
    died on a NOT NULL constraint halfway through the transaction, naming a
    table and nothing else: the operator was told the restore had failed and
    not which row, nor which link, nor what was missing from the archive. A
    zone served locally, whose signing authority the archive does not carry,
    is the case that reaches this first.

    A column that accepts an empty value keeps its silence: the reference may
    point at a row a later section of this same restore creates, and
    `relink_references` resolves it again once everything exists.

    An archive older than the identities (before 2.230) names the row by the
    source's number alone. The archive is still restored: an existing row
    keeps its link (True is returned), a new one is left out.
    """
    if column.nullable:
        return False
    identity = row.get(f'{name}{REFERENCE_SUFFIX}')
    if not identity:
        state = sa_inspect(instance) if instance is not None else None
        if state is not None and state.persistent and getattr(instance, attribute, None) is not None:
            return True
        why = ("an archive older than 2.230" if f'{name}{REFERENCE_SUFFIX}' not in row
               else "the row it named was gone when the archive was written")
        raise UnplaceableLegacyRow(
            f"{_row_label(section_name, section, row)} was left out: its "
            f"{section.references[name]} link is a number from another database "
            f"({why}), and the row cannot exist without it")
    raise RestoreValidationError(
        f"Invalid backup: {section_name}.{name} points at a "
        f"{section.references[name]} row this installation does not have "
        f"({identity or 'and the archive carries no identity for it'}), and "
        "the column requires one; nothing has been changed")


def _fields_as_stored(value: Any, label: str = 'HSM provider', dropped=None) -> Any:
    """HSM configuration: each sensitive value under this installation's key. A value in the
    source's ciphertext only that key opens: dropped, so the provider shows it as missing."""
    from models.hsm import HsmProvider, _is_sensitive_key
    from utils.encryption import decrypt_value, is_encrypted
    try:
        fields = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
    if not isinstance(fields, dict):
        return value
    for field, secret in list(fields.items()):
        if (_is_sensitive_key(field) and isinstance(secret, str) and secret
                and is_encrypted(secret) and not decrypt_value(secret)):
            del fields[field]
            logger.warning("Restore: %s lost field %s, encrypted under another "
                           "installation's key: enter it again", label, field)
            if dropped is not None:
                dropped.append(f"{label}: {field}")
    # Never added to the session: only its encoding of the column is wanted
    provider = HsmProvider()
    provider.set_config(fields)
    return provider.config


def _secret_as_stored(section, name: str, value: Any, *, label: str = 'HSM provider',
                      dropped=None) -> Any:
    """The archive's cleartext, in the shape the column holds it here.

    A secret is assigned by its manifest name, which is the model's own
    attribute. Where that is a property over a private column, the setter
    re-encrypts with this installation's key and the cleartext is what it
    wants. Where it is a plain column, it depends on the column, and the
    manifest is where that is written down:

    * a column the application reads directly gets the cleartext, because
      that is what the application reads: `pyotp.TOTP(user.totp_secret)`,
      the Argon2 hashes of the backup codes.
      Encrypting those would hand the application a ciphertext it never
      decrypts, and a restored account whose MFA can no longer be verified;
    * a column the application keeps encrypted gets it back encrypted, with
      the layer the application writes it with. Assigning the cleartext there
      put an ACME account key, a deployment SSH key, a SCEP challenge, an
      Intune client secret and a webhook signing secret into the database
      readable: a restore taken and put back on the same installation
      silently undid its own at-rest protection.
    """
    layer = section.stored.get(name)
    if not value or layer is None:
        return value
    if layer == 'fields':
        return _fields_as_stored(value, label, dropped)
    if layer == 'master':
        from security.encryption import encrypt_text
        return encrypt_text(value)
    if layer == 'database':
        from utils.encryption import encrypt_if_needed
        return encrypt_if_needed(value)
    raise RestoreValidationError(
        f"The manifest asks for {name} to be stored as '{layer}', which is "
        "not a layer this version writes")


# The widest integer a database column holds: PostgreSQL's bigint, and the
# ceiling SQLite stores as an INTEGER. Anything past it is not a value some
# backend would take and another would not, it is not a value at all.
_INTEGER_LIMIT = 2 ** 63 - 1


def _refuse_container(value: Any, column, where: str) -> None:
    # Only a JSON column holds a list or an object; the value is not echoed (it may be a secret).
    # column None: a secret property over a private column, which takes text
    if isinstance(value, (list, dict)) and (column is None or not isinstance(column.type, JSON)):
        raise RestoreValidationError(
            f"Invalid backup: {where} holds {_a_kind_of(value)} "
            "where this column takes a single value")


# The encrypted private key of an archive: an object of hex text (BackupService._encrypt_private_key).
# Its salt and nonce have had these lengths in bytes in every release; the ciphertext is never empty.
_KEY_BLOB = 'private_key_pem_encrypted'
_KEY_BLOB_PARTS = {'salt': 32, 'nonce': 12, 'ciphertext': None}


def _kind_of(value: Any) -> str:
    return {list: 'list', dict: 'object', bool: 'boolean', str: 'text'}.get(type(value), 'number')


def _a_kind_of(value: Any) -> str:
    kind = _kind_of(value)
    return f"{'an' if kind[0] in 'aeiou' else 'a'} {kind}"


def _is_key_part(value: Any, length) -> bool:
    try:
        size = len(bytes.fromhex(value))
    except (TypeError, ValueError):
        return False
    return size == length if length is not None else size > 0


def _refuse_unreadable_handled(name: str, value: Any, where: str) -> None:
    """A field a dedicated restorer reads itself: a PEM is text, the encrypted key an object
    of hex text; either may be absent. The value is never echoed (it may be a secret)."""
    if value is None:
        return
    if name == _KEY_BLOB:
        if isinstance(value, dict) and (not value or all(
                _is_key_part(value.get(part), length) for part, length in _KEY_BLOB_PARTS.items())):
            return
        raise RestoreValidationError(
            f"Invalid backup: {where} holds {_a_kind_of(value)} that is not an encrypted key "
            f"(an object of {', '.join(_KEY_BLOB_PARTS)} in hexadecimal, the salt of 32 bytes, "
            "the nonce of 12)")
    if not isinstance(value, str):
        raise RestoreValidationError(
            f"Invalid backup: {where} holds {_a_kind_of(value)} where this field takes text")


def _holds_nul(value: Any) -> bool:
    """Whether a text in ``value``, at any depth and keys included, holds U+0000."""
    if isinstance(value, str):
        return NUL in value
    if isinstance(value, dict):
        return any(_holds_nul(k) or _holds_nul(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_holds_nul(item) for item in value)
    return False


def _without_nul(value: Any, clashes: Optional[List[bool]] = None) -> Any:
    """``value`` through escape_nul; a key rewritten onto another key of its object appends
    to ``clashes`` (one of the two values is lost)."""
    if isinstance(value, str):
        return escape_nul(value)
    if isinstance(value, dict):
        rewritten = {}
        for key, item in value.items():
            new_key = _without_nul(key)
            if new_key in rewritten and clashes is not None:
                clashes.append(True)
            rewritten[new_key] = _without_nul(item, clashes)
        return rewritten
    if isinstance(value, list):
        return [_without_nul(item, clashes) for item in value]
    return value


def _shown(name: str) -> str:
    """An archive's field or key name as a report line may hold it: control characters
    escaped, at most NAME_SHOWN characters."""
    shown = ''.join(c if unicodedata.category(c) != 'Cc' else f'\\x{ord(c):02x}' for c in name)
    return shown if len(shown) <= NAME_SHOWN else shown[:NAME_SHOWN] + '...'


def _mapping_fields_with_nul(mapping: Dict[str, Any]) -> List[str]:
    """The keys of ``mapping`` whose key or value holds a NUL; one level down in a mapping
    value (configuration.settings), so a field is a setting rather than the whole section."""
    fields = []
    for key, value in mapping.items():
        if isinstance(value, dict) and not _holds_nul(key):
            fields.extend(f"{_shown(key)}.{_shown(escape_nul(inner))}"
                          for inner, held in value.items() if _holds_nul(inner) or _holds_nul(held))
        elif _holds_nul(key) or _holds_nul(value):
            fields.append(_shown(escape_nul(key)))
    return fields


def _merged_identities(section_name: str, rows) -> List[str]:
    """The identity fields under which two archived rows of the section become one once
    rewritten: each such field is named, the rows are not."""
    section = SECTIONS.get(section_name)
    if section is None or not section.identity:
        return []
    seen: Dict[tuple, set] = {}
    merged = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        before = tuple(row.get(field) for field in section.identity)
        after = tuple(_without_nul(value) for value in before)
        try:
            # Rows already alike before the rewrite are not the NUL's doing
            if after in seen and before not in seen[after]:
                merged.append('.'.join(section.identity))
            seen.setdefault(after, set()).add(before)
        except TypeError:
            continue    # a list or an object as identity: refused by refuse_containers_in_columns
    return sorted(set(merged))


def _fields_taken(section_name: str):
    """Field names a restorer of the section reads: columns, handled and secret fields and
    references; None when the section has no manifest entry (nothing is said ignored)."""
    section = SECTIONS.get(section_name)
    if section is None:
        return None
    columns, _attribute_of = _mapping_of(load_model(section))
    taken = set(columns) | set(section.handled.values()) | set(section.secrets)
    return taken | {f'{name}{REFERENCE_SUFFIX}' for name in section.references}


# What the report says of a field holding a NUL, by who reads the field
_NUL_TEXT = {
    'column': "a NUL character, which PostgreSQL cannot store in text, was restored as the two "
              "characters \\0",
    # A restorer may read a field of an older archive that no column takes: not said ignored
    'unknown': "a field no column takes held a NUL character; where the restore reads it, it is "
               "restored as the two characters \\0",
    'nobody': "a field no column takes, ignored, holding a NUL character",
}


def _reader_of(name, taken) -> str:
    """Who reads a row's field: a column, nobody (no code spells a name holding a NUL), or unknown."""
    if taken is None or name in taken:
        return 'column'
    return 'nobody' if _holds_nul(name) else 'unknown'


# Fields named one by one in the report; past this many, a count
NUL_WARNING_FIELDS = 20
# Characters of an archive's field name a warning shows
NAME_SHOWN = 64


def escape_nul_in_archive(backup_data, sections) -> List[str]:
    """Every text of ``sections`` (rows and mappings, keys and identities included, at any
    depth) through escape_nul, before anything compares or follows them: a reference still
    names the row it named. For a PostgreSQL target only, which stores no NUL.

    One warning per section.field, the value never echoed; one more per identity under which
    two archived rows become one."""
    from ..section_store import SectionStore, section_kind
    fields: List[str] = []
    merged: List[str] = []
    for section_name in sorted(sections):
        kind = section_kind(backup_data, section_name)
        if kind == 'mapping':
            mapping = backup_data[section_name]
            hit = _mapping_fields_with_nul(mapping)
            if hit:
                rewritten = {}
                for key, value in mapping.items():
                    clashes: List[bool] = []
                    new_key = escape_nul(key) if isinstance(key, str) else key
                    if new_key in rewritten:
                        merged.append(section_name)
                    rewritten[new_key] = _without_nul(value, clashes)
                    if clashes:
                        merged.append(f"{section_name}.{_shown(str(new_key))}")
                backup_data[section_name] = rewritten
                fields.extend((f"{section_name}.{name}", 'column') for name in hit)
            continue
        if kind != 'list':
            continue
        rows = (backup_data.iter_rows(section_name) if isinstance(backup_data, SectionStore)
                else backup_data[section_name])
        taken = _fields_taken(section_name)
        hit = {}
        for row in rows:
            if isinstance(row, dict):
                for name, value in row.items():
                    if _holds_nul(name) or _holds_nul(value):
                        hit.setdefault(_shown(escape_nul(name)), _reader_of(name, taken))
            elif _holds_nul(row):
                hit.setdefault('(row)', 'column')
        if hit:
            # Loaded only when it holds one: written back through the store
            loaded = backup_data[section_name]
            merged.extend(f"{section_name}.{field}"
                          for field in _merged_identities(section_name, loaded))
            for row in loaded:
                names = set()
                for name, value in (row.items() if isinstance(row, dict) else ()):
                    clashes = []
                    _without_nul(value, clashes)
                    if clashes:
                        merged.append(f"{section_name}.{_shown(escape_nul(name))}")
                    if escape_nul(name) in names:
                        merged.append(section_name)
                    names.add(escape_nul(name))
            backup_data[section_name] = _without_nul(loaded)
            fields.extend((f"{section_name}.{name}", reader) for name, reader in hit.items())
    merged = list(dict.fromkeys(merged))
    warnings = [f"{field}: {_NUL_TEXT[reader]}" for field, reader in fields[:NUL_WARNING_FIELDS]]
    if len(fields) > NUL_WARNING_FIELDS:
        warnings.append(f"{len(fields) - NUL_WARNING_FIELDS} more fields held a NUL character, "
                        "restored the same way")
    warnings.extend(
        f"{field}: two archived rows or keys hold the same value once their NUL characters "
        "are rewritten as \\0, and are restored as one" for field in merged)
    return warnings


def refuse_containers_in_columns(backup_data) -> None:
    """RestoreValidationError, before any write, for a value no restorer of the row can take.

    A list or an object in a non JSON column, or in a secret property over a column of
    another name; a field the dedicated restorers read themselves (`Section.handled`) that is
    neither absent nor of the shape they read: text for a PEM, an object for the encrypted key."""
    from ..section_store import SectionStore, section_kind
    for section_name, section in SECTIONS.items():
        if section_kind(backup_data, section_name) != 'list':
            continue
        columns, _attribute_of = _mapping_of(load_model(section))
        handled = set(section.handled.values())
        rows = (backup_data.iter_rows(section_name) if isinstance(backup_data, SectionStore)
                else backup_data[section_name])
        for row in rows:
            if not isinstance(row, dict):
                continue
            for name, value in row.items():
                column = columns.get(name)
                if name in handled:
                    _refuse_unreadable_handled(name, value, f"{section_name}.{name}")
                elif column is not None and name not in section.handled:
                    _refuse_container(value, column, f"{section_name}.{name}")
                elif (column is None and name in section.secrets
                      and section.stored.get(name) != 'fields'):
                    # A `fields` secret is an object; none is a property over another column today
                    _refuse_container(value, None, f"{section_name}.{name}")


def _coerce(value: Any, column, where: str) -> Any:
    """Turn an archived value back into what the column holds."""
    if value is None:
        return None

    kind = column.type
    _refuse_container(value, column, where)
    try:
        if isinstance(kind, LargeBinary) and isinstance(value, str):
            return base64.b64decode(value)
        if isinstance(kind, (DateTime, Date)) and isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is not None:
                parsed = parsed.replace(tzinfo=None)
            return parsed.date() if isinstance(kind, Date) and not isinstance(kind, DateTime) else parsed
        if isinstance(kind, Boolean) and not isinstance(value, bool):
            if isinstance(value, str):  # bool("false") is True
                raise ValueError('text in a boolean column')
            return bool(value)
        if isinstance(kind, (Integer, Numeric)) and isinstance(value, str):
            # Left alone, "twenty-two" reached SQLite, which stores it, and
            # PostgreSQL, which refuses it: the same archive restored or
            # failed depending on the backend underneath.
            return int(value) if isinstance(kind, Integer) else float(value)
        if isinstance(kind, Integer) and isinstance(value, int):
            # A number no database column can hold. Caught here, where the
            # section and the column can still be named, rather than as an
            # OverflowError from the driver halfway through the transaction.
            if not -_INTEGER_LIMIT <= value <= _INTEGER_LIMIT:
                raise RestoreValidationError(
                    f"Invalid backup: {where} is out of range for this "
                    "column")
    except RestoreValidationError:
        raise
    except (ValueError, TypeError, OverflowError) as exc:
        raise RestoreValidationError(
            f"Invalid backup: {where} does not hold a value this column can "
            f"take ({value!r})") from exc
    return value


def relink_references(backup_data: Dict[str, Any], plan: RestorePlan) -> Dict[str, int]:
    """Point every reference at the row it names, now that all rows exist.

    Sections are applied in an order that cannot satisfy everything at once: a
    certificate authority is restored before the HSM key it uses, so the first
    pass had nothing to resolve its link against and left it empty. Rather
    than order the sections by hand and hope, the references are resolved a
    second time against the database as the restore has just left it.
    """
    plan.refresh()
    relinked: Dict[str, int] = {}

    for section_name, rows in backup_data.items():
        section = SECTIONS.get(section_name)
        if section is None or not section.references or not isinstance(rows, list):
            continue

        model = load_model(section)
        columns, attribute_of = _mapping_of(model)

        changed = 0
        for row in rows:
            tick()
            if not isinstance(row, dict):
                continue
            target_id = plan.existing_id(section_name, row)
            if target_id is None:
                continue
            instance = db.session.get(model, target_id)
            if instance is None:
                continue
            kept = plan.kept_columns(section_name, instance)
            for column in section.references:
                if column not in row or (f'{column}{REFERENCE_SUFFIX}' not in row
                                         and row.get(column) is not None):
                    continue      # no identity to resolve: the first pass decided
                attribute = attribute_of.get(column, column)
                if column in kept or attribute in kept:
                    continue      # part of a final state a merge keeps here (kept_states)
                resolved = plan.resolve(section_name, row, column)
                if resolved is None and column in columns and not columns[column].nullable:
                    continue      # kept, as `_unplaceable_reference` keeps it
                if getattr(instance, attribute, None) != resolved:
                    setattr(instance, attribute, resolved)
                    changed += 1
        if changed:
            relinked[section_name] = changed

    db.session.flush()
    return relinked
