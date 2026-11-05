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


RULES = {
    # A Cloudflare provider and a Route 53 one are two providers.
    'dns_providers': _Rule('name', lambda row, here: row.get('provider_type') == here.provider_type),
    # By (directory, account URL) once registered, by label before that.
    'acme_client_accounts': _Rule(
        'label',
        lambda row, here: _account_key(row) is None or _account_key(row) == _account_key_here(here),
        _account_key, _account_key_here),
    # By URL, then name.
    'webhook_endpoints': _Rule('name', lambda row, here: row.get('url') == here.url,
                               lambda row: (row.get('url'),), lambda here: (here.url,)),
}


def rename_clashing_rows(backup_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Rename, in the archive, the rows that would land on another row's name.

    References carried by identity follow the rename. Returns one entry per
    row restored under a name other than its own.
    """
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
        final, reasons = _place(section_name, rule, rows)
        for index, row in enumerate(rows):
            if final[index] != row[rule.column]:
                renamed.append({'section': section_name, 'from': row[rule.column],
                                'to': final[index], 'reason': reasons[index]})
                logger.warning("Restore: %s %r restored as %r (%s)", section_name,
                               row[rule.column], final[index], reasons[index])
        _follow_references(backup_data, section_name, rule, before, final)
        for index, row in enumerate(rows):
            row[rule.column] = final[index]
    return renamed


def _place(section_name, rule, rows):
    """The name each archived row is restored under, and why it changed."""
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
    used = set(final.values())
    originals = {row[rule.column] for row in rows}
    for index, row in enumerate(rows):
        if index in final:
            continue
        wanted = row[rule.column]
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
    return final, reasons


def _length(section_name, rule):
    column = load_model(SECTIONS[section_name]).__table__.columns[rule.column]
    return getattr(column.type, 'length', None) or NAME_MAX_LENGTH


def _follow_references(backup_data, section_name, rule, before, final):
    """Point each identity carried beside a reference at the row's new name.

    An identity matching several archived rows names the first of them.
    """
    for name, section in SECTIONS.items():
        columns = [c for c, target in section.references.items() if target == section_name]
        rows = backup_data.get(name)
        if not columns or not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            for column in columns:
                identity = row.get(f'{column}{REFERENCE_SUFFIX}')
                if not isinstance(identity, dict) or rule.column not in identity:
                    continue
                index = next((i for i, archived in enumerate(before)
                              if all(archived.get(k) == v for k, v in identity.items())), None)
                if index is not None and final[index] != identity[rule.column]:
                    row[f'{column}{REFERENCE_SUFFIX}'] = {**identity, rule.column: final[index]}
