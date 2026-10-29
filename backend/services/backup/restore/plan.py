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

    # -- building ---------------------------------------------------------

    @classmethod
    def build(cls, backup_data: Dict[str, Any]) -> 'RestorePlan':
        plan = cls()
        plan._validate_shape(backup_data)
        plan._index_target_rows(backup_data)
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
                   if row.get(field) in (None, '')]
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
            self.target_ids[name] = _index_of(name, section)

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
            self.target_ids[name] = _index_of(name, section)

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
            # An archive written before references carried identities: the
            # number is all there is, and it means nothing here.
            if row.get(column) is not None:
                self.warnings.append(
                    f"{section_name}.{column} has no identity in this archive; "
                    "the reference was dropped rather than pointed at a "
                    "different row")
            return None

        return self._id_of(target, identity, translate=translate)

    def existing_id(self, section_name: str, row: Dict[str, Any]) -> Optional[Any]:
        """The id of the row here that this archived row is, if it exists."""
        section = SECTIONS.get(section_name)
        if section is None:
            return None
        index = self.target_ids.get(section_name, {})

        if section.identity == ('id',):
            # A section that holds one row for the whole installation: the
            # SMTP configuration, the Active Directory connector. Its identity
            # is the primary key, which the archive carries from the source
            # and means nothing here, so a restore found no row to update and
            # added a second one -- an installation restored twice ended up
            # with two configurations and used whichever the query returned.
            return next(iter(index.values()), None)

        found = index.get(_identity_key(row, section.identity,
                                        _temporal_identity(section_name)))
        if found is None and _identified_by_a_reference(section):
            found = index.get(self._identity_here(section_name, row))
        return found

    def _id_of(self, section_name: str, identity: Dict[str, Any], *,
               translate: bool) -> Optional[Any]:
        """The id here of the row an archived identity names."""
        section = SECTIONS.get(section_name)
        if section is None:
            return None
        index = self.target_ids.get(section_name, {})
        found = index.get(_identity_key(identity, section.identity,
                                        _temporal_identity(section_name)))
        if found is None and translate and _identified_by_a_reference(section):
            archived = self._archived_row(section_name, identity)
            if archived is not None:
                found = index.get(self._identity_here(section_name, archived))
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


def _index_of(section_name: str, section: Section) -> Dict[Tuple, Any]:
    model = load_model(section)
    mapper = sa_inspect(model)
    primary = [column.key for column in mapper.primary_key]
    if len(primary) != 1:
        return {}
    # Read the same way the archive is: a backend that hands a timestamp back
    # as text would otherwise never match the archive's spelling of it.
    temporal = _temporal_identity(section_name)
    index = {}
    for row in model.query.all():
        key = tuple(_normalise(getattr(row, field, None), field in temporal)
                    for field in section.identity)
        index[key] = getattr(row, primary[0])
    return index


def _referenced_sections(backup_data: Dict[str, Any]) -> set:
    """Sections pointed at by a reference in the archive."""
    targets = set()
    for name in backup_data:
        section = SECTIONS.get(name)
        if section:
            targets.update(section.references.values())
    return targets
