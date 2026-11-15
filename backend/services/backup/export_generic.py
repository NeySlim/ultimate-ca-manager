"""Exporting a section from the manifest, rather than by hand.

Every column a model has is written unless the manifest excludes it in
writing, so a column added to a model lands in the next archive on its own.
Values are read from the mapped attribute, never from a model property: a
property that decrypts also hides a failure to decrypt, which is how archives
ended up carrying None where a credential belonged.
"""
import base64
import importlib
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Dict, Iterator, List, Optional

from sqlalchemy import inspect as sa_inspect

from .errors import BackupExportError
from .key_material import as_pem, decrypt_stored_fields, decrypt_stored_key, decrypt_stored_secret
from .manifest import SECTIONS, Section

logger = logging.getLogger(__name__)

# Suffix carrying the stable identity of a referenced row, next to the
# numeric foreign key the source happened to use.
REFERENCE_SUFFIX = '_ref'


_TRANSIENT_KEY = ('AcmeClientOrder', '_pending_key')


def _key_material_columns():
    """(model, attribute) of the columns holding base64 key material under the master key."""
    from security.encryption import MASTER_KEY_COLUMNS
    return {(name, attribute) for _module, name, attribute, fmt in MASTER_KEY_COLUMNS if fmt == 'b64'}


def load_model(section: Section):
    module_name, class_name = section.model.split(':')
    return getattr(importlib.import_module(module_name), class_name)


def _serialise(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return base64.b64encode(value).decode()
    if isinstance(value, Decimal):
        return str(value)
    return value


def identity_of(row, section: Section) -> Dict[str, Any]:
    """The values that identify this row on another installation."""
    return {name: _serialise(getattr(row, name, None)) for name in section.identity}


# Rows read per query: a section is never loaded whole, whatever its size
EXPORT_BATCH = 500


def iter_model_pages(model, batch: Optional[int] = None) -> Iterator[list]:
    """A table's rows in primary-key order, one page per query (keyset pagination)."""
    mapper = sa_inspect(model)
    primary = list(mapper.primary_key)
    if len(primary) != 1:
        rows = model.query.order_by(*primary).all()
        if rows:
            yield rows
        return
    column = primary[0]
    attribute = mapper.get_property_by_column(column).key
    size = batch or EXPORT_BATCH
    last = None
    while True:
        query = model.query.order_by(column)
        if last is not None:
            query = query.filter(column > last)
        page = query.limit(size).all()
        if not page:
            return
        last = getattr(page[-1], attribute)
        yield page
        if len(page) < size:
            return


class IdentityIndex:
    """Primary key to stable identity, per section, for the page being written.

    `prefetch` reads the identities a page names in one query and forgets the
    previous page's, so its size is bounded by a page, not by the table.
    """

    def __init__(self):
        self._by_section: Dict[str, Dict[Any, Dict[str, Any]]] = {}

    def of(self, section_name: str, key: Any):
        if key is None:
            return None
        table = self._by_section.get(section_name)
        if table is None or key not in table:
            self.prefetch(section_name, (key,), keep=True)
            table = self._by_section[section_name]
        return table.get(key)

    def prefetch(self, section_name: str, keys, keep: bool = False) -> None:
        wanted = {key for key in keys if key is not None}
        table = self._by_section.get(section_name) if keep else None
        table = {} if table is None else table
        if wanted:
            table.update(self._read(section_name, wanted))
            for key in wanted:
                table.setdefault(key, None)
        self._by_section[section_name] = table

    @staticmethod
    def _read(section_name: str, keys) -> Dict[Any, Dict[str, Any]]:
        section = SECTIONS[section_name]
        model = load_model(section)
        mapper = sa_inspect(model)
        primary = list(mapper.primary_key)
        if len(primary) != 1:
            return {}
        key_attr = mapper.get_property_by_column(primary[0]).key
        found = {}
        ordered = sorted(keys, key=repr)
        for start in range(0, len(ordered), EXPORT_BATCH):
            for row in model.query.filter(primary[0].in_(ordered[start:start + EXPORT_BATCH])):
                found[getattr(row, key_attr)] = identity_of(row, section)
        return found


def export_section(section_name: str, index: IdentityIndex,
                   warnings: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Read one section whole: `iter_section` collected, for callers that need a list."""
    return list(iter_section(section_name, index, warnings))


def iter_section(section_name: str, index: IdentityIndex,
                 warnings: Optional[List[str]] = None,
                 extra: Optional[Callable[[Any], Dict[str, Any]]] = None) -> Iterator[Dict[str, Any]]:
    """Read one section a page at a time: every column, the secrets in the clear,
    the references carried by identity as well as by number.

    `extra(row)` is a dedicated exporter's part of the row, laid over the
    manifest's columns."""
    section = SECTIONS[section_name]
    model = load_model(section)
    mapper = sa_inspect(model)

    # Mapped attribute per column: `_credentials` rather than the property
    # `credentials`, which would decrypt (and swallow failures) for us.
    attribute_of = {}
    for prop in mapper.column_attrs:
        for column in prop.columns:
            attribute_of[column.key] = prop.key
    key_material = _key_material_columns()
    columns = [column.key for column in mapper.columns]

    # Oldest first, the order a restore pairs the rows of a shared identity in
    for page in iter_model_pages(model):
        named: Dict[str, set] = {}
        for column, target in section.references.items():
            named.setdefault(target, set()).update(
                getattr(row, attribute_of.get(column, column), None) for row in page)
        for target, keys in named.items():
            index.prefetch(target, keys)
        for row in page:
            data = _export_row(section_name, section, model, row, columns, attribute_of,
                               key_material, index, warnings)
            yield {**data, **extra(row)} if extra is not None else data


def _export_row(section_name, section, model, row, columns, attribute_of, key_material,
                index, warnings):
    data: Dict[str, Any] = {}
    for name in columns:
        if name in section.exclude or name in section.handled:
            # Excluded on purpose, or written by the dedicated exporter
            # under the name the archive has always used.
            continue
        value = getattr(row, attribute_of.get(name, name))
        data[name] = _serialise(value)

    label = _label(section_name, row, section)
    for secret in section.secrets:
        stored_attr = attribute_of.get(secret, secret)
        if not hasattr(row, stored_attr):
            stored_attr = f'_{secret}'
        if not hasattr(row, stored_attr):
            raise BackupExportError(
                f"Section '{section_name}' declares a secret {secret!r} the "
                "model does not hold")
        stored = getattr(row, stored_attr)
        if (model.__name__, stored_attr) in key_material:
            # Base64 key material under the master key, carried as the PEM
            try:
                data[secret] = as_pem(decrypt_stored_key(stored, label=label), label=label) if stored else None
            except BackupExportError as exc:
                if (model.__name__, stored_attr) != _TRANSIENT_KEY:
                    raise
                # A finalization's key: one this key cannot open is left out, not the backup
                message = (f"ACME order {getattr(row, 'id', '?')}: its pending key could not "
                           "be read and is not in the archive")
                logger.warning("Backup: %s (%s)", message, exc)
                if warnings is not None:
                    warnings.append(message)
                data[secret] = None
            continue
        decrypt = decrypt_stored_fields if section.stored.get(secret) == 'fields' else decrypt_stored_secret
        data[secret] = decrypt(stored, label=f"{label} ({secret})")

    for column, target in section.references.items():
        data[f'{column}{REFERENCE_SUFFIX}'] = index.of(
            target, getattr(row, attribute_of.get(column, column), None))

    if section_name == 'deploy_bindings':
        data[CHAIN_VARIANT_FINGERPRINT] = _pinned_cross_fingerprint(row.chain_variant)
    return data


CHAIN_VARIANT_FINGERPRINT = 'chain_variant_fingerprint'


def _pinned_cross_fingerprint(chain_variant):
    """Fingerprint of the cross-certificate a binding is pinned to; its id is renumbered on restore."""
    kind, _, ident = (chain_variant or '').partition(':')
    if kind != 'cross' or not ident.isdigit():
        return None
    from models.ca_cross_certificate import CACrossCertificate
    row = CACrossCertificate.query.get(int(ident))
    return row.fingerprint_sha256 if row else None


def _label(section_name: str, row, section: Section) -> str:
    """A name an administrator can act on, for error messages."""
    values = [str(getattr(row, name, '')) for name in section.identity]
    return f"{section_name} {'/'.join(v for v in values if v)}".strip()
