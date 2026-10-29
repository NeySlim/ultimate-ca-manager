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
import logging
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.types import (
    Boolean,
    Date,
    DateTime,
    Integer,
    LargeBinary,
    Numeric,
)

from models import db

from ..export_generic import CHAIN_VARIANT_FINGERPRINT, REFERENCE_SUFFIX, load_model
from ..manifest import SECTIONS
from .plan import RestorePlan, RestoreValidationError

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


def apply_columns(instance, section_name: str, row: Dict[str, Any],
                  plan: RestorePlan) -> None:
    """Put every column the archive carries for this row onto `instance`.

    This is the whole of "restoring a row", and it is deliberately the same
    call for a row being created and for one that already exists: the restore
    used to set a hand-picked subset of fields on an existing certificate or
    CA, so its subject, serial, SANs, template or CRL cadence stayed at
    whatever the target happened to hold.

    The columns the manifest marks `handled` are left out: a dedicated
    restorer owns them because it is the one holding the archive's master key
    (the PEMs and the private key). Everything else comes from here.
    """
    section = SECTIONS[section_name]
    columns, attribute_of = _mapping_of(type(instance))
    _apply_row(section_name, section, instance, row, columns, attribute_of, plan)


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

    applied = 0
    for row in rows:
        target_id = plan.existing_id(section_name, row)
        instance = db.session.get(model, target_id) if target_id is not None else None
        if instance is None:
            instance = model()
            db.session.add(instance)

        _apply_row(section_name, section, instance, row, columns, attribute_of, plan)
        applied += 1

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


def _apply_row(section_name, section, instance, row, columns, attribute_of, plan):
    for name, value in row.items():
        if name.startswith('_') or name.endswith(REFERENCE_SUFFIX):
            continue          # internal marker, or the identity of a reference
        if name in section.handled:
            continue          # the dedicated restorer owns this column
        if name == 'id':
            continue          # the target keeps its own key
        column = columns.get(name)
        if column is None:
            continue          # a column this version does not have

        if name in section.references:
            resolved = plan.resolve(section_name, row, name)
            if resolved is None and row.get(name) is not None:
                _unplaceable_reference(section_name, section, name, row, column)
            setattr(instance, attribute_of.get(name, name), resolved)
            continue

        if name in section.secrets:
            setattr(instance, name, _secret_as_stored(section, name, value))
            continue

        if section_name == 'deploy_bindings' and name == 'chain_variant':
            value = _restored_chain_variant(row, value, plan)

        setattr(instance, attribute_of.get(name, name),
                _coerce(value, column, f"{section_name}.{name}"))
    for column, value in legacy_defaults(section_name, row, plan).items():
        setattr(instance, attribute_of.get(column, column), value)


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
        plan.chain_variant_fallbacks.append(str(value))
        return 'auto'
    return f'cross:{target.id}'


def _unplaceable_reference(section_name, section, name, row, column) -> None:
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
    """
    if column.nullable:
        return
    identity = row.get(f'{name}{REFERENCE_SUFFIX}')
    raise RestoreValidationError(
        f"Invalid backup: {section_name}.{name} points at a "
        f"{section.references[name]} row this installation does not have "
        f"({identity or 'and the archive carries no identity for it'}), and "
        "the column requires one; nothing has been changed")


def _secret_as_stored(section, name: str, value: Any) -> Any:
    """The archive's cleartext, in the shape the column holds it here.

    A secret is assigned by its manifest name, which is the model's own
    attribute. Where that is a property over a private column, the setter
    re-encrypts with this installation's key and the cleartext is what it
    wants. Where it is a plain column, it depends on the column, and the
    manifest is where that is written down:

    * a column the application reads directly gets the cleartext, because
      that is what the application reads: `pyotp.TOTP(user.totp_secret)`,
      `json.loads(provider.config)`, the Argon2 hashes of the backup codes.
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


def _coerce(value: Any, column, where: str) -> Any:
    """Turn an archived value back into what the column holds."""
    if value is None:
        return None

    kind = column.type
    try:
        if isinstance(kind, LargeBinary) and isinstance(value, str):
            return base64.b64decode(value)
        if isinstance(kind, (DateTime, Date)) and isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is not None:
                parsed = parsed.replace(tzinfo=None)
            return parsed.date() if isinstance(kind, Date) and not isinstance(kind, DateTime) else parsed
        if isinstance(kind, Boolean) and not isinstance(value, bool):
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
        mapper = sa_inspect(model)
        attribute_of = {}
        for prop in mapper.column_attrs:
            for column in prop.columns:
                attribute_of[column.key] = prop.key

        changed = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            target_id = plan.existing_id(section_name, row)
            if target_id is None:
                continue
            instance = db.session.get(model, target_id)
            if instance is None:
                continue
            for column in section.references:
                if column not in row:
                    continue
                resolved = plan.resolve(section_name, row, column)
                attribute = attribute_of.get(column, column)
                if getattr(instance, attribute, None) != resolved:
                    setattr(instance, attribute, resolved)
                    changed += 1
        if changed:
            relinked[section_name] = changed

    db.session.flush()
    return relinked
