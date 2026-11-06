"""What the restore decides before it writes anything.

Two questions are answered here, on the archive alone and on the target's
current state, never by writing: is every row of every section something this
version can apply, and which target row does each archived row and each
archived reference correspond to.

The second question is the one the old restore got wrong in the way that
hurts most quietly: it wrote the source's numeric ids into the target, so a
group membership, an API key or a client certificate could land on whichever
user happened to hold that id here.
"""
import base64
from datetime import date, datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import inspect as sa_inspect

from ..export_generic import REFERENCE_SUFFIX, load_model
from ..manifest import SECTIONS, Section

logger = logging.getLogger(__name__)


class RestoreValidationError(ValueError):
    """The archive holds something this version will not apply.

    Raised before the first write, so the message can say plainly that
    nothing was changed.
    """


# Sections whose payload is a mapping, not a list of rows.
_MAPPING_SECTIONS = {'configuration', 'https_server'}


class RestorePlan:
    """The decisions taken before the first write."""

    def __init__(self):
        self.target_ids: Dict[str, Dict[Tuple, Any]] = {}
        self.rows: Dict[str, List[Dict[str, Any]]] = {}
        self.warnings: List[str] = []
        self.chain_variant_fallbacks: List[str] = []
        # Archived rows by the identity they carry, built once per section it
        # is asked for: a reference is resolved for every row of every section
        # that declares one, and walking the archive again each time would
        # make a restore quadratic in what it carries.
        self._archived_by_identity: Dict[str, Dict[Tuple, Dict[str, Any]]] = {}
        # Source row numbers mean something here only on the same database.
        self.same_installation = False
        # Rows an older archive cannot place, and secrets it carries under a
        # key this installation does not hold: both told in the result.
        self.left_out: List[str] = []
        self.dropped_fields: List[str] = []
        # Ids a restorer wrote, per section: what a replayed repair may touch
        self.written: Dict[str, set] = {}
        # Rows here sharing an identity, oldest first, and those whose identity
        # misses a part, per section (see `_index_of`)
        self.shared: Dict[str, Dict[Tuple, List[Any]]] = {}
        self.incomplete: Dict[str, List[Any]] = {}
        # The archived rows that claimed a row here, per identity, in order; and
        # the row each archived row was written to, which a second pass reuses
        self._claims: Dict[Tuple, List[int]] = {}
        self._placed: Dict[Tuple[str, int], Any] = {}

    # -- building ---------------------------------------------------------

    @classmethod
    def build(cls, backup_data: Dict[str, Any], pruned=frozenset()) -> 'RestorePlan':
        """`pruned`: the sections a replacing restore prunes; `rows_to_remove` tells theirs."""
        from ..installation import same_installation

        plan = cls()
        plan.same_installation = same_installation(backup_data)
        plan._validate_shape(backup_data)
        plan._index_target_rows(backup_data)
        plan._warn_shared_identities(pruned)
        return plan

    def _validate_shape(self, backup_data: Dict[str, Any]) -> None:
        """Every section is the shape this version applies, row by row."""
        for name, value in backup_data.items():
            if name in ('metadata', 'checksum'):
                continue
            section = SECTIONS.get(name)
            if section is None:
                # Not a section this version knows: reported elsewhere, and
                # not a reason to refuse an archive from a neighbouring
                # version that carries more than we do.
                continue

            if name in _MAPPING_SECTIONS:
                if not isinstance(value, dict):
                    raise RestoreValidationError(
                        f"Invalid backup: section '{name}' should be an object")
                continue

            if not isinstance(value, list):
                raise RestoreValidationError(
                    f"Invalid backup: section '{name}' should be a list of rows")

            for position, row in enumerate(value):
                if not isinstance(row, dict):
                    raise RestoreValidationError(
                        f"Invalid backup: row {position} of section '{name}' is "
                        "not an object")
                self._validate_identity(name, section, row, position)
            self.rows[name] = value

    def _validate_identity(self, name: str, section: Section, row: Dict[str, Any],
                           position: int) -> None:
        """A row with no identity cannot be matched to a row here.

        Where the column allows it, the row is still restorable: it is written
        as a new row, and nothing can point at it. Refusing the whole archive
        over one such row would make an installation carrying rows older than
        the column that identifies them impossible to restore at all.

        Where the column does not allow it, the row cannot be written at all,
        and saying "it will be restored as a new row" was a promise the insert
        then broke: the transaction died on a constraint violation halfway
        through, and the operator was told the restore had failed without
        being told which row did it. That case is named here, before anything
        is written.
        """
        if section.identity == ('id',):
            return  # singleton configuration rows
        missing = [field for field in section.identity
                   if missing_identity_value(name, field, row.get(field))]
        if not missing:
            return

        unwritable = [field for field in missing
                      if not self._identity_column_accepts_nothing(section, field)]
        if unwritable:
            raise RestoreValidationError(
                f"Invalid backup: row {position} of section '{name}' has no "
                f"{', '.join(unwritable)}, which the column requires: the row "
                "cannot be restored")

        self.warnings.append(
            f"row {position} of section '{name}' has no "
            f"{', '.join(missing)}: it will be restored as a new row and "
            "nothing can point at it"
        )

    @staticmethod
    def _identity_column_accepts_nothing(section: Section, field: str) -> bool:
        """Whether that identity column tolerates a row without a value.

        A column this version does not know is treated as tolerant: an
        archive from another version must not be refused over a column that
        is not ours to judge.
        """
        try:
            model = load_model(section)
            column = sa_inspect(model).local_table.columns.get(field)
        except Exception:
            return True
        if column is None:
            return True
        return bool(column.nullable)

    def _index_target_rows(self, backup_data: Dict[str, Any]) -> None:
        """Map each section's stable identity to the id it has *here*."""
        for name in set(self.rows) | _referenced_sections(backup_data):
            section = SECTIONS.get(name)
            if section is None or name in _MAPPING_SECTIONS:
                continue
            self.target_ids[name], self.shared[name], self.incomplete[name] = _index_of(name, section)

    def _warn_shared_identities(self, pruned) -> None:
        for name in sorted(set(self.shared) - set(pruned)):
            for key, ids in self.shared[name].items():
                self.warnings.append(shared_identity_warning(name, key, ids, 'left as they are'))

    def refresh(self, section_names=None) -> None:
        """Rebuild the identity indexes from the database as it is now.

        The plan is built before anything is written, so it only knows the
        rows that existed then. Once the restore has created the rows the
        archive carries, a reference pointing at one of them can be resolved,
        which the first pass could not do.
        """
        for name in (section_names or list(self.target_ids)):
            section = SECTIONS.get(name)
            if section is None or name in _MAPPING_SECTIONS:
                continue
            self.target_ids[name], self.shared[name], self.incomplete[name] = _index_of(name, section)

    # -- using ------------------------------------------------------------

    def resolve(self, section_name: str, row: Dict[str, Any],
                column: str) -> Optional[Any]:
        """The target id a reference points at, or None.

        The archive carries both the source id and the identity of the row it
        pointed at; only the identity means anything here.
        """
        return self._resolve(section_name, row, column, translate=True)

    def _resolve(self, section_name: str, row: Dict[str, Any], column: str,
                 *, translate: bool) -> Optional[Any]:
        section = SECTIONS.get(section_name)
        if section is None:
            return None
        target = section.references.get(column)
        if target is None:
            return row.get(column)

        identity = row.get(f'{column}{REFERENCE_SUFFIX}')
        if not identity:
            # The number alone means nothing here: no link rather than another row's
            if row.get(column) is not None:
                why = ("an archive older than this link's identity"
                       if f'{column}{REFERENCE_SUFFIX}' not in row
                       else "the row it named was gone when the archive was written")
                self.warnings.append(
                    f"{row_label(section_name, section, row)}: its {column} link was "
                    f"left empty ({why})")
            return None

        return self._id_of(target, identity, translate=translate)

    def id_for(self, section_name: str, identity: Dict[str, Any]) -> Optional[Any]:
        """The id here of the row an archived identity names, from the last refresh."""
        return self._id_of(section_name, identity, translate=True)

    def existing_id(self, section_name: str, row: Dict[str, Any]) -> Optional[Any]:
        """The id of the row here that this archived row is, if it exists."""
        section = SECTIONS.get(section_name)
        if section is None:
            return None
        placed = self._placed.get((section_name, id(row)))
        if placed is not None and sa_inspect(placed).persistent:
            return sa_inspect(placed).identity[0]
        index = self.target_ids.get(section_name, {})

        if section.identity == ('id',):
            # A section that holds one row for the whole installation: the
            # SMTP configuration, the Active Directory connector. Its identity
            # is the primary key, which the archive carries from the source
            # and means nothing here, so a restore found no row to update and
            # added a second one -- an installation restored twice ended up
            # with two configurations and used whichever the query returned.
            return next(iter(index.values()), None)

        if not _identified_by_a_reference(section):
            return self._claimed(section_name, _identity_key(
                row, section.identity, _temporal_identity(section_name)), row)
        # By what the references name first; the source's numbers only when
        # they are this database's own and still name the same rows.
        key = self._identity_here(section_name, row)
        if key not in index and self.source_numbers_hold(section_name, row):
            key = _identity_key(row, section.identity, _temporal_identity(section_name))
        return self._claimed(section_name, key, row)

    def _claimed(self, section_name: str, key: Tuple, row: Dict[str, Any]) -> Optional[Any]:
        """The row here for that identity, by rank: the n-th archived row of it takes the n-th oldest."""
        index = self.target_ids.get(section_name, {})
        ids = self.shared.get(section_name, {}).get(key) or ([index[key]] if key in index else [])
        return self.rank(section_name, key, row, ids)

    def rank(self, section_name: str, key: Tuple, row: Dict[str, Any], ids: List[Any]) -> Optional[Any]:
        """Of `ids` (oldest first), the one this archived row takes: beyond them, None, a new row."""
        claims = self._claims.setdefault((section_name, key), [])
        if id(row) not in claims:
            claims.append(id(row))
        position = claims.index(id(row))
        return ids[position] if position < len(ids) else None

    def place(self, section_name: str, row: Dict[str, Any], instance) -> None:
        """Record the row here an archived row was written to: a later pass finds that one."""
        self._placed[(section_name, id(row))] = instance

    def source_numbers_hold(self, section_name: str, row: Dict[str, Any]) -> bool:
        """Whether the numbers in this row's identity name, here, the rows it carries.

        Only for an archive of this very database, and only when each number
        points at a row with the identity the archive wrote beside it.
        """
        if not self.same_installation or not isinstance(row, dict):
            return False
        section = SECTIONS.get(section_name)
        if section is None:
            return False
        from models import db

        for field_name in section.identity:
            target_name = section.references.get(field_name)
            if target_name is None:
                continue
            number = row.get(field_name)
            identity = row.get(f'{field_name}{REFERENCE_SUFFIX}')
            if number is None or not isinstance(identity, dict) or not identity:
                return False
            target = SECTIONS.get(target_name)
            if target is None:
                return False
            try:
                with db.session.no_autoflush:
                    here = db.session.get(load_model(target), number)
            except Exception:
                return False
            temporal = _temporal_identity(target_name)
            if here is None or tuple(
                    _normalise(getattr(here, name, None), name in temporal)
                    for name in target.identity) != _identity_key(
                        identity, target.identity, temporal):
                return False
        return True

    def _id_of(self, section_name: str, identity: Dict[str, Any], *,
               translate: bool) -> Optional[Any]:
        """The id here of the row an archived identity names."""
        section = SECTIONS.get(section_name)
        if section is None:
            return None
        index = self.target_ids.get(section_name, {})
        raw = _identity_key(identity, section.identity, _temporal_identity(section_name))
        if not _identified_by_a_reference(section):
            return index.get(raw)
        archived = self._archived_row(section_name, identity)
        found = None
        if translate and archived is not None:
            found = index.get(self._identity_here(section_name, archived))
        if found is None and self.source_numbers_hold(section_name, archived):
            found = index.get(raw)
        return found

    def _identity_here(self, section_name: str,
                       row: Dict[str, Any]) -> Tuple:
        """An archived row's identity, spelled the way the row holds it here.

        A section can be identified by what it points at: an HSM key is its
        provider and its key identifier. The numbers in the archive are the
        source's and the row restored here holds this installation's, so the
        two spellings never met -- and a reference *to* such a section found
        nothing. An authority came back without the HSM key it signs with,
        and a second restore wrote the key a second time rather than
        recognising the one it had just put there.

        Only one level is translated: the reference columns of the identity
        are resolved by their own identity alone, which is what the section
        they point at is indexed by.
        """
        section = SECTIONS[section_name]
        values = []
        for field_name in section.identity:
            if field_name in section.references:
                values.append(self._resolve(section_name, row, field_name,
                                            translate=False))
            else:
                values.append(row.get(field_name))
        temporal = _temporal_identity(section_name)
        return tuple(_normalise(value, field in temporal)
                     for field, value in zip(section.identity, values))

    def _archived_row(self, section_name: str,
                      identity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """The row of the archive that carries this identity.

        An identity written beside a reference holds the identity columns and
        nothing else; the row it was taken from is what also holds, for each
        of those columns that is itself a reference, the identity *it* points
        at.
        """
        fields = SECTIONS[section_name].identity
        index = self._archived_by_identity.get(section_name)
        if index is None:
            temporal = _temporal_identity(section_name)
            index = {_identity_key(row, fields, temporal): row
                     for row in self.rows.get(section_name) or []}
            self._archived_by_identity[section_name] = index
        return index.get(_identity_key(identity, fields,
                                       _temporal_identity(section_name)))


def _identity_key(values: Dict[str, Any], fields: Tuple[str, ...],
                  temporal: frozenset = frozenset()) -> Tuple:
    return tuple(_normalise(values.get(field), field in temporal)
                 for field in fields)


# Which identity columns of a section hold a date or a timestamp, asked of
# the mapper once per section rather than once per row.
_TEMPORAL_IDENTITY: Dict[str, frozenset] = {}


def _temporal_identity(section_name: str) -> frozenset:
    """The identity columns of a section that hold a moment in time.

    Only those are read back from their text form. A name, a reference, a
    serial number is a string and stays one: `datetime.fromisoformat` accepts
    far more than a timestamp, and two identities that are not the same value
    at all -- a template called `20260914` and one called `2026-09-14`, two
    spellings of a serial number -- became the same key, so the index lost
    one of them and an archived row was applied over the wrong target.
    """
    cached = _TEMPORAL_IDENTITY.get(section_name)
    if cached is not None:
        return cached

    from sqlalchemy.types import Date, DateTime

    section = SECTIONS.get(section_name)
    fields = frozenset()
    if section is not None:
        try:
            columns = sa_inspect(load_model(section)).local_table.columns
            fields = frozenset(
                field for field in section.identity
                if isinstance(getattr(columns.get(field), 'type', None),
                              (Date, DateTime)))
        except Exception:
            fields = frozenset()
    _TEMPORAL_IDENTITY[section_name] = fields
    return fields


def _identified_by_a_reference(section: Section) -> bool:
    """Whether this section's identity holds a number that means nothing here."""
    return any(field in section.references for field in section.identity)


def row_label(section_name: str, section: Section, row: Dict[str, Any]) -> str:
    values = [str(row.get(field)) for field in section.identity if row.get(field) not in (None, '')]
    return f"{section_name} {'/'.join(values)}".strip()


def _normalise(value: Any, temporal: bool = False) -> Any:
    """One spelling for a value that identifies a row, whichever side it
    comes from.

    The archive carries a timestamp as an ISO string with a `T` in it; the
    database hands back a `datetime`, whose `str()` uses a space. Compared as
    text they never matched, so a section identified partly by a timestamp --
    a key recovery request is (certificate, when it was asked for) -- found no
    existing row to update, created a second one, and then had it deleted
    again by the replacement pass, which saw an identity the archive "did not
    hold". The section came out of a restore empty.

    `temporal` says the value comes from a column that holds a moment in
    time, and only then is its text form read back as one: see
    `_temporal_identity` for what reading everything back cost.
    """
    if isinstance(value, bytes):
        return base64.b64encode(value).decode()
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    text = str(value)
    if not temporal:
        return text
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).isoformat()
    except ValueError:
        return text


def missing_identity_value(section_name: str, field: str, value: Any) -> bool:
    """Whether an identity part is absent: None, or ''.

    Except '' in a column that requires a value and defaults to '' (an
    SNI-less endpoint's `sni_hostname`), where it is one.
    """
    if value is None:
        return True
    if value != '':
        return False
    nullable = _NULLABLE.get((section_name, field))
    if nullable is None:
        try:
            column = sa_inspect(load_model(SECTIONS[section_name])).local_table.columns.get(field)
            default = getattr(getattr(column, 'default', None), 'arg', None)
            nullable = column is None or bool(column.nullable) or default != ''

        except Exception:
            nullable = True
        _NULLABLE[(section_name, field)] = nullable
    return nullable


_NULLABLE: Dict[Tuple[str, str], bool] = {}


def _index_of(section_name: str, section: Section):
    """(identity to its oldest row here, the rows of each identity several share, the rows
    whose identity misses a part), all oldest first.

    A table without a unique constraint on its identity can hold two rows of
    one. An identity missing a part identifies nothing: no archived row is
    matched to such a row, and a replacement removes it.
    """
    model = load_model(section)
    mapper = sa_inspect(model)
    primary = [column.key for column in mapper.primary_key]
    if len(primary) != 1:
        return {}, {}, []
    # Read the same way the archive is: a backend that hands a timestamp back
    # as text would otherwise never match the archive's spelling of it.
    temporal = _temporal_identity(section_name)
    singleton = section.identity == ('id',)
    rows, incomplete = {}, []
    for row in model.query.order_by(getattr(model, primary[0])).all():
        values = [getattr(row, field, None) for field in section.identity]
        if not singleton and any(missing_identity_value(section_name, field, value)
                                 for field, value in zip(section.identity, values)):
            incomplete.append(getattr(row, primary[0]))
            continue
        key = tuple(_normalise(value, field in temporal) for field, value in zip(section.identity, values))
        rows.setdefault(key, []).append(getattr(row, primary[0]))
    index = {key: ids[0] for key, ids in rows.items()}
    shared = {key: ids for key, ids in rows.items() if len(ids) > 1 and not singleton}
    return index, shared, incomplete


def shared_identity_warning(section_name: str, key: Tuple, ids: List[Any], fate: str,
                            others: Optional[List[Any]] = None) -> str:
    others = ids[1:] if others is None else others
    message = (f"{section_name} {'/'.join(key)}: {len(ids)} rows here share this "
               f"{'/'.join(SECTIONS[section_name].identity)} (id {', '.join(map(str, ids))}); "
               "the archive's rows of it go to them oldest first")
    return f"{message}, and the others (id {', '.join(map(str, others))}) are {fate}" if others else message


def _referenced_sections(backup_data: Dict[str, Any]) -> set:
    """Sections pointed at by a reference in the archive."""
    targets = set()
    for name in backup_data:
        section = SECTIONS.get(name)
        if section:
            targets.update(section.references.values())
    return targets
