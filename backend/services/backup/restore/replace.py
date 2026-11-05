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
"""
import logging
from typing import Any, Dict, List, Set, Tuple

from sqlalchemy import inspect as sa_inspect

from models import db

from ..export_generic import load_model
from ..manifest import SECTIONS
from .plan import RestorePlan, _normalise, _temporal_identity

logger = logging.getLogger(__name__)

# Rows that exist for the instance itself rather than for its data: removing
# them would lock the operator out of the server they are restoring.
PROTECTED = {
    'users': lambda row: False,          # handled by the caller's own guard
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

    archived = set()
    for row in archived_rows:
        archived.update(_archived_identities(section_name, section, row, plan))
    present = plan.target_ids.get(section_name) or {}
    return [target_id for key, target_id in present.items() if key not in archived]


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


def replace_sections(backup_data: Dict[str, Any], plan: RestorePlan,
                     sections: Set[str], *, keep: Dict[str, Set[Any]] = None
                     ) -> Dict[str, int]:
    """Remove, from the sections the archive carries, what it does not hold.

    Runs inside the restore's transaction, so a failure here undoes the whole
    restore rather than leaving an instance with rows deleted and nothing put
    back.
    """
    keep = keep or {}
    removed: Dict[str, int] = {}

    for section_name in deletion_order(sections):
        archived_rows = backup_data.get(section_name)
        if archived_rows is None or not isinstance(archived_rows, list):
            continue          # not carried by this archive: not ours to prune

        doomed = [target_id for target_id in rows_to_remove(section_name, archived_rows, plan)
                  if target_id not in keep.get(section_name, set())]
        if not doomed:
            continue

        model = load_model(SECTIONS[section_name])
        mapper = sa_inspect(model)
        primary = list(mapper.primary_key)[0]
        count = model.query.filter(primary.in_(doomed)).delete(
            synchronize_session=False)
        db.session.flush()
        removed[section_name] = count
        logger.info("Restore: removed %d row(s) from '%s' that the archive "
                    "does not carry", count, section_name)

    return removed
