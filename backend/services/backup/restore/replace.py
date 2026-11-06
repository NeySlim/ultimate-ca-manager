"""Making a restore a replacement rather than a merge.

The wiki has always said a restore *replaces* the instance, and it did not:
every restorer upserted what the archive held and left everything else alone.
Restoring after a compromise therefore kept the administrator account, the API
key or the client certificate that was added after the snapshot — the very
rows the restore was meant to remove.

What is removed is deliberately narrow: only sections the archive actually
carries, only rows that can be identified, and never a section the archive
does not mention at all (an archive taken without the optional histories must
not wipe them).

The removal runs before the archive's rows are written, so a name or a slug a
removed row held is free for the row that replaces it. What points at a removed
row is decided here, the same way on every database engine: see
`DEPENDENT_TABLES`.
"""
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import delete, select, true, update

from models import db

from ..export_generic import load_model
from ..manifest import SECTIONS
from .conflict import RestoreConflictError, describe_row
from .plan import RestorePlan, _normalise, _temporal_identity, shared_identity_warning

logger = logging.getLogger(__name__)

# Rows that exist for the instance itself rather than for its data: removing
# them would lock the operator out of the server they are restoring.
PROTECTED = {
    'users': lambda row: False,          # handled by the caller's own guard
}

# Sections a replacing restore merges and never prunes, and why.
MERGED_ONLY: Dict[str, str] = {
    'compromised_keys': 'a block list: a key known here as compromised stays refused, archived or not',
}

# Which section a table belongs to, and which sections each one points into.
# Built once: the mappers do not change between restores.
_SECTION_OF_TABLE: Dict[str, str] = {}
_POINTS_AT: Dict[str, Set[str]] = {}


def _index_tables() -> None:
    if _SECTION_OF_TABLE:
        return
    for name, section in SECTIONS.items():
        try:
            _SECTION_OF_TABLE[load_model(section).__table__.name] = name
        except Exception:
            continue


def _points_at(section_name: str) -> Set[str]:
    """The sections a row of this one holds a foreign key into.

    Taken from the tables themselves rather than from the manifest's
    `references`, which is a smaller set on purpose: a column that already
    says the same thing on every installation is not a reference and is not
    declared as one. `acme_client_orders.account_id` is exactly that, an ACME
    account id the protocol defines, and it is also a real foreign key into
    `acme_accounts`. Ordering the deletions by the declarations alone put the
    accounts first and left PostgreSQL refusing the delete, taking a
    replacing restore with it.
    """
    cached = _POINTS_AT.get(section_name)
    if cached is not None:
        return cached

    section = SECTIONS[section_name]
    targets = set(section.references.values())
    try:
        table = load_model(section).__table__
    except Exception:
        _POINTS_AT[section_name] = targets
        return targets

    for column in table.columns:
        for foreign_key in column.foreign_keys:
            named = _SECTION_OF_TABLE.get(foreign_key.column.table.name)
            if named is not None and named != section_name:
                targets.add(named)
    _POINTS_AT[section_name] = targets
    return targets


def deletion_order(section_names: Set[str]) -> List[str]:
    """Sections ordered so that a row is removed before what it points at."""
    _index_tables()
    remaining = set(section_names)
    ordered: List[str] = []
    while remaining:
        # A section can go once nothing left points at it
        free = [name for name in remaining
                if not any(name in _points_at(other)
                           for other in remaining
                           if other != name)]
        if not free:
            # A cycle: order within it cannot be decided, so take the rest as
            # they come and let the database complain if it must.
            ordered.extend(sorted(remaining))
            break
        for name in sorted(free):
            ordered.append(name)
            remaining.discard(name)
    return ordered


def rows_to_remove(section_name: str, archived_rows: List[Dict[str, Any]],
                   plan: RestorePlan) -> List[Any]:
    """Primary keys of the rows here that the archive does not carry."""
    section = SECTIONS[section_name]
    if section.identity == ('id',):
        return []          # singleton configuration: nothing to prune

    archived = Counter()
    for row in archived_rows:
        archived.update(_archived_identities(section_name, section, row, plan))
    present = plan.target_ids.get(section_name) or {}
    shared = plan.shared.get(section_name) or {}
    doomed = [target_id for key, target_id in present.items()
              if key not in archived and key not in shared]
    # An identity several rows share keeps, oldest first, as many as the archive carries
    for key, ids in shared.items():
        gone = ids[archived.get(key, 0):]
        doomed.extend(gone)
        plan.warnings.append(shared_identity_warning(section_name, key, ids, 'removed', gone))
    # No archived row can be one whose identity misses a part
    incomplete = plan.incomplete.get(section_name) or []
    if incomplete:
        doomed.extend(incomplete)
        plan.warnings.append(
            f"{section_name}: {len(incomplete)} row(s) here without a complete "
            f"{'/'.join(section.identity)} (id {', '.join(map(str, incomplete))}) are removed, "
            "then those the archive carries are restored from it as new rows")
    return doomed


def _archived_identities(section_name: str, section, row: Dict[str, Any],
                        plan: RestorePlan) -> Set[Tuple]:
    """Every spelling of an archived row's identity that could match here.

    A section identified by what it points at carries the source's numbers;
    they are a spelling here only when `plan.source_numbers_hold` says the
    archive is this database's and the numbers still name the same rows.
    """
    resolved, raw = [], []
    for field_name in section.identity:
        raw.append(row.get(field_name))
        if field_name in section.references:
            resolved.append(plan.resolve(section_name, row, field_name))
        else:
            resolved.append(row.get(field_name))

    temporal = _temporal_identity(section_name)
    by_reference = any(name in section.references for name in section.identity)
    spellings = set()
    if not by_reference or plan.source_numbers_hold(section_name, row):
        spellings.add(tuple(_normalise(value, name in temporal)
                            for name, value in zip(section.identity, raw)))
    if any(value is not None for value in resolved):
        spellings.add(tuple(_normalise(value, name in temporal)
                            for name, value in zip(section.identity, resolved)))
    return spellings


# Tables a replacing restore does not prune itself, and why their rows may go.
# A row pointing at a removed row loses that link where the column allows it,
# and goes with the row otherwise (see REMOVED_WITH_TARGET).
DEPENDENT_TABLES: Dict[str, str] = {
    'crl_metadata': 'regenerated from the authorities',
    'ocsp_responses': 'a response cache',
    'est_signer_certs': 'EST key generators, issued again by their CA on first use',
    'user_sessions': 'live sessions, revoked after every restore anyway',
    'pro_sso_sessions': 'live SSO sessions',
    'webauthn_challenges': 'single-use challenges',
    'acme_orders': 'in-flight protocol state of the ACME server',
    'acme_authorizations': 'in-flight protocol state, tied to orders',
    'acme_challenges': 'in-flight protocol state, tied to authorizations',
    'acme_proxy_dns_challenges': 'expected TXT values of in-flight proxy orders',
    # Carried by default since 2.250, so pruned with the rest; listed for an
    # archive without them (older, or an include map). Unlinked as deleting
    # the certificate, account or user they name does.
    'acme_client_orders': 'carried since 2.250; an older archive lacks them',
    'approval_requests': 'carried since 2.250; an older archive lacks them',
    'key_recovery_requests': 'carried since 2.250; an older archive lacks them',
    # Optional sections, absent from an archive unless asked for.
    'msca_requests': 'history, carried only when asked for',
    'scep_requests': 'history, carried only when asked for',
    'discovery_scan_runs': 'history, carried only when asked for',
    'discovered_certificates': 'history, carried only when asked for',
    'revoked_serials': 'a revocation outlives its certificate; the serial stays revoked',
    # Queues: a pending delivery would reach whichever row takes the number
    'webhook_deliveries': 'delivery queue, removed with its endpoint as deleting it does',
    'deploy_deliveries': 'delivery queue, removed with its binding as deleting it does',
    'pro_sso_saml_message_ids': 'replay cache of SAML message ids',
}

# Integer links the schema holds without a foreign key, handled as if it had one:
# SQLite hands a removed row's id to the next row inserted.
SOFT_LINKS = (
    ('certificates', 'related_certificate_id', 'certificates', 'id'),
    ('scep_profiles', 'template_id', 'certificate_templates', 'id'),
    ('scep_requests', 'profile_id', 'scep_profiles', 'id'),
    ('acme_eab_credentials', 'created_by_user_id', 'users', 'id'),
    ('acme_eab_credentials', 'revoked_by_user_id', 'users', 'id'),
    ('acme_dns_update_keys', 'created_by_user_id', 'users', 'id'),
    ('acme_proxy_dns_challenges', 'acme_client_account_id', 'acme_client_accounts', 'id'),
    ('pro_sso_saml_message_ids', 'provider_id', 'pro_sso_providers', 'id'),
    ('revoked_serials', 'certificate_id', 'certificates', 'id'),
    ('key_recovery_requests', 'cert_id', 'certificates', 'id'),
    ('webhook_deliveries', 'endpoint_id', 'webhook_endpoints', 'id'),
    ('deploy_deliveries', 'binding_id', 'deploy_bindings', 'id'),
    ('deploy_deliveries', 'binding_id', 'crl_deploy_bindings', 'id'),
)

# An optional link the schema never enforced is emptied wherever it lives.
_SOFT_COLUMNS = {(table, column) for table, column, _target, _key in SOFT_LINKS}

# A link whose column names one table or another, told apart by a second column.
_SOFT_SCOPE = {
    ('deploy_deliveries', 'binding_id', 'deploy_bindings'): ('binding_type', 'certificate'),
    ('deploy_deliveries', 'binding_id', 'crl_deploy_bindings'): ('binding_type', 'crl'),
}


def link_scope(dependent, column, named):
    """The condition a row of `dependent` meets to point into `named`'s table."""
    scope = _SOFT_SCOPE.get((dependent.name, column.name, named.table.name))
    return dependent.c[scope[0]] == scope[1] if scope else true()

# A request still open on a removed certificate is closed, never repointed.
CLOSED_WITH_TARGET = {('key_recovery_requests', 'cert_id')}

# Links whose row goes with the row it names although the column allows none:
# an approval of a certificate that is gone, as deleting the certificate does.
REMOVED_WITH_TARGET = {('approval_requests', 'certificate_id')}

_CHUNK = 500
_FOREIGN_KEYS_INTO: Optional[Dict[str, List[Tuple[Any, Any, Any]]]] = None


def _foreign_keys_into(table_name: str) -> List[Tuple[Any, Any, Any]]:
    """(dependent table, its column, the column it names) for every key into a table."""
    global _FOREIGN_KEYS_INTO
    if _FOREIGN_KEYS_INTO is None:
        from services.database_admin.helpers import _force_register_all_models
        _force_register_all_models()
        index: Dict[str, List[Tuple[Any, Any, Any]]] = {}
        tables = db.metadata.tables
        for table in tables.values():
            for column in table.columns:
                for foreign_key in column.foreign_keys:
                    index.setdefault(foreign_key.column.table.name, []).append(
                        (table, column, foreign_key.column))
        for name, column, target, key in SOFT_LINKS:
            if name in tables and target in tables:
                index.setdefault(target, []).append(
                    (tables[name], tables[name].c[column], tables[target].c[key]))
        _FOREIGN_KEYS_INTO = index
    return _FOREIGN_KEYS_INTO.get(table_name, [])


def _chunks(values: Iterable[Any]) -> Iterable[List[Any]]:
    values = list(values)
    for start in range(0, len(values), _CHUNK):
        yield values[start:start + _CHUNK]


def _table_of(section_name: str):
    return load_model(SECTIONS[section_name]).__table__


def _primary(table):
    columns = list(table.primary_key.columns)
    return columns[0] if len(columns) == 1 else None


def _select(columns, where_column, values, scope=None) -> List[Tuple]:
    found = []
    scope = true() if scope is None else scope
    for chunk in _chunks(values):
        found.extend(db.session.execute(
            select(*columns).where(where_column.in_(chunk), scope)).all())
    return found


@dataclass
class Replacement:
    """What a replacing restore removes, decided before the first write."""

    order: List[str]
    doomed: Dict[str, Set[Any]]
    pruned: Set[str]
    deferred: Dict[str, Set[Any]] = field(default_factory=dict)
    # Rows that give their name up to an archived row: they must go before the writes
    displaced: Dict[str, Set[Any]] = field(default_factory=dict)
    removed: Dict[str, int] = field(default_factory=dict)
    cleared: Dict[str, int] = field(default_factory=dict)
    unlinked: Dict[str, int] = field(default_factory=dict)
    closed: Dict[str, int] = field(default_factory=dict)

    def report(self) -> Dict[str, Any]:
        return {'removed': dict(self.removed), 'cleared_dependents': dict(self.cleared),
                'unlinked_dependents': dict(self.unlinked),
                'closed_dependents': dict(self.closed)}


def plan_replacement(backup_data: Dict[str, Any], plan: RestorePlan, sections: Set[str], *,
                     keep: Optional[Dict[str, Set[Any]]] = None,
                     displaced: Optional[Dict[str, Set[Any]]] = None) -> Replacement:
    """The rows each pruned section loses, in the order they can go."""
    _index_tables()
    keep = keep or {}
    displaced = displaced or {}
    pruned = {name for name in sections
              if isinstance(backup_data.get(name), list) and name not in MERGED_ONLY}
    doomed: Dict[str, Set[Any]] = {}
    for name in pruned:
        ids = set(rows_to_remove(name, backup_data[name], plan)) | set(displaced.get(name, ()))
        ids -= set(keep.get(name, ()))
        if ids:
            doomed[name] = ids
    return Replacement(order=[name for name in deletion_order(set(doomed))],
                       doomed=doomed, pruned=pruned,
                       displaced={name: set(ids) for name, ids in displaced.items() if ids})


def remove_before_writes(replacement: Replacement) -> Replacement:
    """Detach or clear what points at the doomed rows, then remove them.

    A doomed row that a kept row names through a column that cannot be empty
    waits for the writes, which point that row elsewhere.
    """
    _index_tables()
    db.session.flush()
    _defer_what_kept_rows_need(replacement)
    for name, ids in replacement.displaced.items():
        waiting = ids & replacement.deferred.get(name, set())
        if waiting:
            # The archived row would be written over it, and then removed with it
            raise RestoreConflictError(
                f"Refusing to restore: {describe_row(name, next(iter(waiting)))} gives its "
                "name up to an archived row, but a row the restore keeps still points at it. "
                "Nothing has been changed.")
    for name in replacement.order:
        table = _table_of(name)
        _detach_kept_rows(replacement, name, table)
        _release_dependents(replacement, table, _primary(table), replacement.doomed[name], name)
    for name in replacement.order:
        _delete(replacement, name, replacement.doomed[name] - replacement.deferred.get(name, set()))
    db.session.expire_all()
    return replacement


def remove_after_writes(replacement: Replacement) -> Replacement:
    """Remove the rows that had to wait; refused if something still needs one."""
    if not any(replacement.deferred.values()):
        return replacement
    _index_tables()
    db.session.flush()
    for name in replacement.order:
        waiting = replacement.deferred.get(name)
        if not waiting:
            continue
        table = _table_of(name)
        primary = _primary(table)
        for dependent, column, named in _foreign_keys_into(table.name):
            dependent_section = _SECTION_OF_TABLE.get(dependent.name)
            if dependent_section not in replacement.pruned or _primary(dependent) is None:
                continue
            values = {row[0] for row in _select([named], primary, waiting)}
            dependent_primary = _primary(dependent)
            later = replacement.deferred.get(dependent_section, set())
            for row in _select([dependent_primary, column], column, values):
                if row[0] in later:
                    continue
                holder = next(key for key, value in _select([primary, named], named, [row[1]]))
                raise RestoreConflictError(
                    f"Refusing to restore: {describe_row(dependent_section, row[0])} "
                    f"still points at {describe_row(name, holder)}, which the restore "
                    "removes. Nothing has been changed.")
        _delete(replacement, name, waiting)
    db.session.expire_all()
    return replacement


def _defer_what_kept_rows_need(replacement: Replacement) -> None:
    """Doomed rows a kept row names through a required column, and what they need."""
    deferred = defaultdict(set)
    for name, ids in replacement.doomed.items():
        table = _table_of(name)
        primary = _primary(table)
        for dependent, column, named in _foreign_keys_into(table.name):
            dependent_section = _SECTION_OF_TABLE.get(dependent.name)
            if (dependent_section not in replacement.pruned or column.nullable
                    or _primary(dependent) is None
                    or (dependent.name, column.name) in CLOSED_WITH_TARGET):
                continue    # a carried recovery request keeps its status from the archive
            by_value = defaultdict(set)
            for key, value in _select([primary, named], primary, ids):
                by_value[value].add(key)
            gone = replacement.doomed.get(dependent_section, set())
            for key, value in _select([_primary(dependent), column], column, by_value):
                if key not in gone:
                    deferred[name].update(by_value[value])

    # A row that waits keeps what it points at waiting too.
    pending = [(name, set(ids)) for name, ids in deferred.items()]
    while pending:
        name, ids = pending.pop()
        table = _table_of(name)
        primary = _primary(table)
        for column in table.columns:
            for foreign_key in column.foreign_keys:
                target = _SECTION_OF_TABLE.get(foreign_key.column.table.name)
                if target is None or target not in replacement.doomed:
                    continue
                values = {row[0] for row in _select([column], primary, ids) if row[0] is not None}
                target_table = foreign_key.column.table
                needed = {row[0] for row in _select([_primary(target_table)],
                                                    foreign_key.column, values)}
                needed &= replacement.doomed[target]
                fresh = needed - deferred[target]
                if fresh:
                    deferred[target].update(fresh)
                    pending.append((target, fresh))
    replacement.deferred = {name: ids for name, ids in deferred.items() if ids}


def _detach_kept_rows(replacement: Replacement, name: str, table) -> None:
    """Kept rows naming a doomed row through an optional column: the writes set it again."""
    primary = _primary(table)
    ids = replacement.doomed[name]
    for dependent, column, named in _foreign_keys_into(table.name):
        dependent_section = _SECTION_OF_TABLE.get(dependent.name)
        if (dependent_section not in replacement.pruned or not column.nullable
                or _primary(dependent) is None):
            continue
        values = [row[0] for row in _select([named], primary, ids)]
        gone = replacement.doomed.get(dependent_section, set())
        dependent_primary = _primary(dependent)
        kept = [row[0] for row in _select([dependent_primary], column, values)
                if row[0] not in gone]
        for chunk in _chunks(kept):
            db.session.execute(update(dependent).where(dependent_primary.in_(chunk))
                               .values({column.name: None}))


def _release_dependents(replacement: Replacement, table, key_column, keys, owner: str) -> None:
    """Rows of the tables this archive does not prune that point at rows about to go."""
    if not keys:
        return
    for dependent, column, named in _foreign_keys_into(table.name):
        dependent_section = _SECTION_OF_TABLE.get(dependent.name)
        if dependent_section in replacement.pruned:
            continue    # pruned itself, or detached above
        if dependent is table:
            continue    # a row naming another of the same table goes in the same statement
        values = [row[0] for row in _select([named], key_column, keys)]
        if not values:
            continue
        scope = link_scope(dependent, column, named)
        pointing = _select([column], column, values, scope)
        if not pointing:
            continue
        unenforced = (dependent.name, column.name) in _SOFT_COLUMNS and column.nullable
        if dependent.name not in DEPENDENT_TABLES and not unenforced:
            holder = _select([key_column], named, [pointing[0][0]])[0][0]
            raise RestoreConflictError(
                f"Refusing to restore: the archive removes {describe_row(owner, holder)}, "
                f"which {len(pointing)} row(s) of '{dependent.name}' still point at, and "
                "this archive does not carry that table. Nothing has been changed.")
        if (dependent.name, column.name) in CLOSED_WITH_TARGET:
            _close_requests(replacement, dependent, column, values)
            continue
        if column.nullable and (dependent.name, column.name) not in REMOVED_WITH_TARGET:
            for chunk in _chunks(values):
                result = db.session.execute(update(dependent).where(column.in_(chunk), scope)
                                            .values({column.name: None}))
                _count(replacement.unlinked, f'{dependent.name}.{column.name}', result.rowcount)
            continue
        # The rows go: first whatever points at them in turn
        dependent_primary = _primary(dependent)
        if dependent_primary is not None:
            doomed_here = [row[0] for row in _select([dependent_primary], column, values, scope)]
            _release_dependents(replacement, dependent, dependent_primary, doomed_here,
                                dependent.name)
        for chunk in _chunks(values):
            result = db.session.execute(delete(dependent).where(column.in_(chunk), scope))
            _count(replacement.cleared, dependent.name, result.rowcount)


def _close_requests(replacement: Replacement, table, column, values) -> None:
    """Open key recovery requests on a removed certificate are cancelled, with a note."""
    from models.key_recovery import STATUS_APPROVED, STATUS_CANCELLED, STATUS_PENDING
    from utils.datetime_utils import utc_now

    for chunk in _chunks(values):
        result = db.session.execute(
            update(table).where(column.in_(chunk),
                                table.c.status.in_([STATUS_PENDING, STATUS_APPROVED]))
            .values(status=STATUS_CANCELLED, decided_by='restore', decided_at=utc_now(),
                    decision_note='Cancelled by a restore that removed the certificate'))
        _count(replacement.closed, table.name, result.rowcount)


def _delete(replacement: Replacement, name: str, ids: Set[Any]) -> None:
    if not ids:
        return
    table = _table_of(name)
    primary = _primary(table)
    count = 0
    for chunk in _chunks(sorted(ids)):
        count += db.session.execute(delete(table).where(primary.in_(chunk))).rowcount
    replacement.removed[name] = replacement.removed.get(name, 0) + count
    logger.info("Restore: removed %d row(s) from '%s' that the archive does not carry",
                count, name)


def _count(counter: Dict[str, int], key: str, value: int) -> None:
    if value:
        counter[key] = counter.get(key, 0) + value
        logger.info("Restore: %s: %d row(s) pointing at a removed row", key, value)


def replace_sections(backup_data: Dict[str, Any], plan: RestorePlan,
                     sections: Set[str], *, keep: Dict[str, Set[Any]] = None
                     ) -> Dict[str, int]:
    """Remove, from the sections the archive carries, what it does not hold.

    Both phases at once, for a caller with nothing to write in between.
    """
    replacement = plan_replacement(backup_data, plan, sections, keep=keep)
    remove_before_writes(replacement)
    remove_after_writes(replacement)
    return replacement.removed
