"""Archived rows whose name is taken are renamed, never merged.

DNS providers, ACME CA accounts and webhooks are found again by name, unique
since migration 124. An older archive can hold one name twice, and a name
here can belong to something else: each archived row is matched to the row
here that is the same thing, and any other row is given a free name.
"""
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from utils.unique_names import NAME_MAX_LENGTH, suffixed

from ..export_generic import REFERENCE_SUFFIX, load_model
from ..manifest import SECTIONS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Rule:
    column: str
    # Whether an archived row and a row here are the same thing, names aside.
    same: Callable[[Dict[str, Any], Any], bool]
    # What finds that row under another name; None: the name alone does.
    key: Optional[Callable[[Dict[str, Any]], Optional[tuple]]] = None
    key_here: Optional[Callable[[Any], Optional[tuple]]] = None


def _account_key(row):
    return (row.get('directory_url'), row['account_url']) if row.get('account_url') else None


def _account_key_here(account):
    return (account.directory_url, account.account_url) if account.account_url else None


def _same_account(row, here):
    """Same directory, and the same registration or none on either side."""
    return (row.get('directory_url') == here.directory_url
            and (row.get('account_url') or None) == (here.account_url or None))


RULES = {
    # A Cloudflare provider and a Route 53 one are two providers.
    'dns_providers': _Rule('name', lambda row, here: row.get('provider_type') == here.provider_type),
    # By (directory, account URL) once registered, by label and directory before that.
    'acme_client_accounts': _Rule('label', _same_account, _account_key, _account_key_here),
    # By URL, then name.
    'webhook_endpoints': _Rule('name', lambda row, here: row.get('url') == here.url,
                               lambda row: (row.get('url'),), lambda here: (here.url,)),
}


def rename_clashing_rows(backup_data: Dict[str, Any],
                         warnings: Optional[List[str]] = None, *,
                         replacing: frozenset = frozenset(),
                         displaced: Optional[Dict[str, set]] = None) -> List[Dict[str, str]]:
    """Rename, in the archive, the rows that would land on another row's name.

    References carried by identity follow the rename; an ambiguous one is added
    to `warnings`. Returns one entry per row restored under another name. In a
    section a replacing restore prunes (`replacing`), a row here that is not
    the same thing gives its name up instead: its id lands in `displaced`.
    """
    warnings = warnings if warnings is not None else []
    displaced = displaced if displaced is not None else {}
    renamed = []
    for section_name, rule in RULES.items():
        rows = backup_data.get(section_name)
        if not isinstance(rows, list):
            continue
        rows = [row for row in rows
                if isinstance(row, dict) and isinstance(row.get(rule.column), str)]
        if not rows:
            continue
        before = [dict(row) for row in rows]
        final, reasons, given_up = _place(section_name, rule, rows, replacing, backup_data)
        if given_up:
            displaced.setdefault(section_name, set()).update(given_up)
        for index, row in enumerate(rows):
            if final[index] != row[rule.column]:
                renamed.append({'section': section_name, 'from': row[rule.column],
                                'to': final[index], 'reason': reasons[index]})
                logger.warning("Restore: %s %r restored as %r (%s)", section_name,
                               row[rule.column], final[index], reasons[index])
        _follow_references(backup_data, section_name, rule, before, final, warnings)
        for index, row in enumerate(rows):
            row[rule.column] = final[index]
    return renamed


def _place(section_name, rule, rows, pruned=frozenset(), backup_data=None):
    """The name each archived row is restored under, why it changed, and the
    rows here that give their name up to it."""
    model = load_model(SECTIONS[section_name])
    here = model.query.order_by(model.id).all()
    by_name: Dict[str, list] = {}
    for target in here:
        by_name.setdefault(getattr(target, rule.column), []).append(target)
    claimed = set()
    final: Dict[int, str] = {}
    reasons: Dict[int, str] = {}

    def claim(row, name):
        target = next((t for t in by_name.get(name, ())
                       if t.id not in claimed and rule.same(row, t)), None)
        if target is not None:
            claimed.add(target.id)
        return target

    # Same name, same thing: the row here is updated.
    for index, row in enumerate(rows):
        if claim(row, row[rule.column]) is not None:
            final[index] = row[rule.column]

    # Same thing under another name: updated, and keeps its name here.
    if rule.key is not None:
        by_key: Dict[tuple, list] = {}
        for target in here:
            key = rule.key_here(target)
            if key is not None:
                by_key.setdefault(key, []).append(target)
        for index, row in enumerate(rows):
            key = rule.key(row)
            if index in final or key is None:
                continue
            target = next((t for t in by_key.get(key, ()) if t.id not in claimed), None)
            if target is not None:
                claimed.add(target.id)
                final[index] = getattr(target, rule.column)
                reasons[index] = 'same row here under this name'

    # Anything else takes its own name if free, else the first free suffix.
    # A replacing restore removes the rows here nothing claimed: their names are free.
    used = set(final.values())
    originals = {row[rule.column] for row in rows}
    given_up = set()
    for index, row in enumerate(rows):
        if index in final:
            continue
        wanted = row[rule.column]
        holders = [t for t in by_name.get(wanted, ()) if t.id not in claimed]
        if (section_name in pruned and wanted not in used and holders
                and len(holders) == len(by_name[wanted])
                and not _required_by_kept_rows(model, {t.id for t in holders}, pruned,
                                               backup_data or {})):
            given_up.update(t.id for t in holders)
            claimed.update(t.id for t in holders)
            final[index] = wanted
            used.add(wanted)
            continue
        candidate, number = wanted, 2
        while True:
            if candidate not in used and (candidate == wanted or candidate not in originals):
                if candidate not in by_name or claim(row, candidate) is not None:
                    break
            candidate = suffixed(wanted, number, _length(section_name, rule))
            number += 1
        if candidate != wanted:
            reasons[index] = ('name held by another row of the archive' if wanted in used
                              else 'name held here by a different row')
        final[index] = candidate
        used.add(candidate)
    return final, reasons, given_up


def _required_by_kept_rows(model, ids, pruned, backup_data) -> bool:
    """Whether a row the restore keeps, in a pruned section, names one of these
    through a required column. Such a row waits for the writes, so its name
    cannot be handed over first; a row the restore removes does not count.
    """
    from models import db
    from sqlalchemy import select
    from .plan import RestorePlan
    from .replace import _SECTION_OF_TABLE, _foreign_keys_into, _index_tables, _primary, rows_to_remove

    _index_tables()
    plan = None
    for dependent, column, named in _foreign_keys_into(model.__table__.name):
        dependent_section = _SECTION_OF_TABLE.get(dependent.name)
        archived = backup_data.get(dependent_section)
        if (column.nullable or dependent_section not in pruned or _primary(dependent) is None
                or not isinstance(archived, list)):
            continue
        held = select(named).where(model.__table__.c.id.in_(ids))
        pointing = {row[0] for row in db.session.execute(
            select(_primary(dependent)).where(column.in_(held))).all()}
        if not pointing:
            continue
        if plan is None:
            plan = RestorePlan.build(backup_data)
        if pointing - set(rows_to_remove(dependent_section, archived, plan)):
            return True
    return False


def _length(section_name, rule):
    column = load_model(SECTIONS[section_name]).__table__.columns[rule.column]
    return getattr(column.type, 'length', None) or NAME_MAX_LENGTH


def _follow_references(backup_data, section_name, rule, before, final, warnings):
    """Point each identity carried beside a reference at the row's new name.

    An identity matching several archived rows names the first of them: the
    archive does not carry the source id that would tell them apart.
    """
    holders = []     # (where, the mapping holding the identity, its key)
    for name, section in SECTIONS.items():
        columns = [c for c, target in section.references.items() if target == section_name]
        rows = backup_data.get(name)
        if not columns or not isinstance(rows, list):
            continue
        holders.extend((f'{name}.{column}', row, f'{column}{REFERENCE_SUFFIX}')
                       for row in rows if isinstance(row, dict) for column in columns)
    configuration = backup_data.get('configuration')
    refs = configuration.get('settings_refs') if isinstance(configuration, dict) else None
    if isinstance(refs, list):
        holders.extend((f"setting {entry.get('key')}", entry, 'identity') for entry in refs
                       if isinstance(entry, dict) and entry.get('table') == section_name)
    for where, holder, field_name in holders:
        identity = holder.get(field_name)
        if not isinstance(identity, dict) or rule.column not in identity:
            continue
        matches = [i for i, archived in enumerate(before)
                   if all(archived.get(k) == v for k, v in identity.items())]
        index = matches[0] if matches else None
        if len(matches) > 1:
            warnings.append(
                f"{where} names {identity[rule.column]!r}, which "
                f"{len(matches)} archived {section_name} rows hold: it now points "
                f"at the first one, restored as {final[index]!r}")
            logger.warning("Restore: %s", warnings[-1])
        if index is not None and final[index] != identity[rule.column]:
            holder[field_name] = {**identity, rule.column: final[index]}
