"""Settings that name a row by its number, put back under this installation's numbers.

The archive carries, beside each such setting, the identity of the row it names
(`settings_refs`). An older archive carries the number alone: it counts only on
the database it was taken from, and only while that row is still there.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from models import SystemConfig, db

from ..export_generic import identity_of, load_model
from ..manifest import SECTIONS, SETTING_REFERENCES, SettingReference
from .settings import store_setting

logger = logging.getLogger(__name__)

SETTINGS_REFS = 'settings_refs'


def reference_of(key: str) -> Optional[Tuple[SettingReference, 're.Match']]:
    """The declaration a setting key matches, with the match, or None."""
    for reference in SETTING_REFERENCES:
        match = re.fullmatch(reference.pattern, key)
        if match:
            return reference, match
    return None


def _value_names_a_row(section_name: str, value: Any) -> Optional[str]:
    """'id' or 'refid' when the value names a row of that section, else None."""
    text = str(value or '').strip()
    if text.isdigit():
        return 'id' if int(text) else None
    if text and SECTIONS[section_name].identity == ('refid',):
        return 'refid'
    return None


def _row(section_name: str, value: Any, form: str):
    model = load_model(SECTIONS[section_name])
    with db.session.no_autoflush:
        if form == 'id':
            return db.session.get(model, int(str(value).strip()))
        return model.query.filter_by(refid=str(value).strip()).first()


def export_references(settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """`{key, part, table, identity}` for every row a setting names on this installation."""
    entries = []
    for key, value in settings.items():
        found = reference_of(key)
        if found is None:
            continue
        reference, match = found
        parts = []
        if reference.key:
            parts.append(('key', reference.key, match.group(1), 'id'))
        if reference.value:
            form = _value_names_a_row(reference.value, value)
            if form:
                parts.append(('value', reference.value, value, form))
        for part, section_name, named, form in parts:
            row = _row(section_name, named, form)
            entries.append({'key': key, 'part': part, 'table': section_name,
                            'identity': identity_of(row, SECTIONS[section_name]) if row else None})
    return entries


def deferred_keys(configuration: Dict[str, Any]) -> set:
    """The archived settings written once the rows they name exist here."""
    settings = (configuration or {}).get('settings') or {}
    return {key for key in settings if reference_of(key) is not None}


def restore_setting_references(configuration: Dict[str, Any], plan) -> int:
    """Write the deferred settings with this installation's numbers. Returns a count.

    A row this installation does not have empties a value and leaves out a
    setting whose key names it; both are warnings of the plan.
    """
    if not isinstance(configuration, dict):
        return 0
    settings = configuration.get('settings') or {}
    encrypted = set(configuration.get('encrypted_settings') or [])
    carried = configuration.get(SETTINGS_REFS)
    by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for entry in carried if isinstance(carried, list) else []:
        if isinstance(entry, dict) and entry.get('table') in SECTIONS:
            by_key[(entry.get('key'), entry.get('part'))] = entry
    plan.refresh(sorted({entry['table'] for entry in by_key.values()}
                        | {name for reference in SETTING_REFERENCES
                           for name in (reference.key, reference.value) if name}))

    written = 0
    for key in sorted(deferred_keys(configuration)):
        reference, match = reference_of(key)
        value = settings[key]
        new_key = key
        if reference.key:
            number, why = _number_here(plan, by_key, carried, key, 'key', reference.key,
                                       match.group(1), 'id')
            if number is None:
                plan.warnings.append(f"setting {key} was left out: the {reference.key} row "
                                     f"its name carries {why}")
                continue
            new_key = key[:match.start(1)] + str(number) + key[match.end(1):]
        if reference.value:
            form = _value_names_a_row(reference.value, value)
            if form:
                number, why = _number_here(plan, by_key, carried, key, 'value', reference.value,
                                           value, form)
                if number is None:
                    plan.warnings.append(f"setting {key} was emptied: the {reference.value} row "
                                         f"it named {why}, choose it again")
                    value = ''
                elif form == 'id':
                    value = str(number)
        store_setting(new_key, value, encrypted=key in encrypted)
        written += 1
    if written:
        db.session.flush()
    return written


_ABSENT = 'is not on this installation'
_GONE_AT_EXPORT = 'was already gone when the archive was written'
_FOREIGN = 'is named by a number of another installation (an older archive)'
_OTHER_ROW = 'is named by a number another row holds here (an older archive)'


def _number_here(plan, by_key, carried, key, part, section_name, named, form):
    """(the id here of the row a setting names, None) or (None, why not)."""
    if isinstance(carried, list):
        entry = by_key.get((key, part))
        identity = entry.get('identity') if entry else None
        if not isinstance(identity, dict) or not identity:
            return None, _GONE_AT_EXPORT
        number = plan.id_for(section_name, identity)
        return (number, None) if number is not None else (None, _ABSENT)
    # An older archive: a refid holds anywhere, a number only on its own database
    # and only for a row of the archive (the rule of `RestorePlan.source_numbers_hold`)
    if form == 'id' and not plan.same_installation:
        return None, _FOREIGN
    row = _row(section_name, named, form)
    if row is None:
        return None, _ABSENT
    if form == 'id' and plan._archived_row(section_name, identity_of(row, SECTIONS[section_name])) is None:
        return None, _OTHER_ROW
    return row.id, None


def prune_doomed_settings(replacement, plan, rewritten=frozenset()) -> int:
    """Settings naming a row a replacing restore removes: dropped when the number is in
    their key, emptied when it is their value. Run before the removal, while the rows exist."""
    from models import SystemConfig

    doomed = replacement.doomed
    names_cache: Dict[str, set] = {}

    def refids_of(section_name):
        if section_name not in names_cache:
            names_cache[section_name] = set()
            if SECTIONS[section_name].identity == ('refid',) and doomed.get(section_name):
                model = load_model(SECTIONS[section_name])
                names_cache[section_name] = {row.refid for row in model.query.filter(
                    model.id.in_(sorted(doomed[section_name]))).all()}
        return names_cache[section_name]

    def names_doomed(section_name, value, form):
        if form == 'id':
            return int(str(value).strip()) in doomed.get(section_name, ())
        return str(value).strip() in refids_of(section_name)

    touched = 0
    for row in SystemConfig.query.all():
        found = reference_of(row.key)
        if found is None:
            continue
        reference, match = found
        if reference.key and names_doomed(reference.key, match.group(1), 'id'):
            db.session.delete(row)
            if row.key not in rewritten:    # the archive's own value follows
                plan.warnings.append(f"setting {row.key} was removed with the {reference.key} "
                                     "row it belongs to")
            touched += 1
            continue
        form = _value_names_a_row(reference.value, row.value) if reference.value else None
        if form and names_doomed(reference.value, row.value, form):
            if row.key not in rewritten:
                plan.warnings.append(f"setting {row.key} was emptied: the {reference.value} row "
                                     "it named is removed by the restore")
            row.value = ''
            touched += 1
    if touched:
        db.session.flush()
    return touched
