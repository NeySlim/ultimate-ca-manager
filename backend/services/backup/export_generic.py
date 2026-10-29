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
from typing import Any, Dict, List

from sqlalchemy import inspect as sa_inspect

from .errors import BackupExportError
from .key_material import decrypt_stored_secret
from .manifest import SECTIONS, Section

logger = logging.getLogger(__name__)

# Suffix carrying the stable identity of a referenced row, next to the
# numeric foreign key the source happened to use.
REFERENCE_SUFFIX = '_ref'


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


class IdentityIndex:
    """Primary key to stable identity, per section, built once per backup."""

    def __init__(self):
        self._by_section: Dict[str, Dict[Any, Dict[str, Any]]] = {}

    def of(self, section_name: str, key: Any):
        if key is None:
            return None
        table = self._by_section.get(section_name)
        if table is None:
            table = self._build(section_name)
            self._by_section[section_name] = table
        return table.get(key)

    @staticmethod
    def _build(section_name: str) -> Dict[Any, Dict[str, Any]]:
        section = SECTIONS[section_name]
        model = load_model(section)
        mapper = sa_inspect(model)
        primary = [column.key for column in mapper.primary_key]
        if len(primary) != 1:
            return {}
        index = {}
        for row in model.query.all():
            index[getattr(row, primary[0])] = identity_of(row, section)
        return index


def export_section(section_name: str, index: IdentityIndex) -> List[Dict[str, Any]]:
    """Read one section: every column, the secrets in the clear, the
    references carried by identity as well as by number."""
    section = SECTIONS[section_name]
    model = load_model(section)
    mapper = sa_inspect(model)

    # Mapped attribute per column: `_credentials` rather than the property
    # `credentials`, which would decrypt (and swallow failures) for us.
    attribute_of = {}
    for prop in mapper.column_attrs:
        for column in prop.columns:
            attribute_of[column.key] = prop.key

    rows = []
    for row in model.query.all():
        data: Dict[str, Any] = {}
        for column in mapper.columns:
            name = column.key
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
            data[secret] = decrypt_stored_secret(
                getattr(row, stored_attr), label=f"{label} ({secret})")

        for column, target in section.references.items():
            data[f'{column}{REFERENCE_SUFFIX}'] = index.of(
                target, getattr(row, attribute_of.get(column, column), None))

        if section_name == 'deploy_bindings':
            data[CHAIN_VARIANT_FINGERPRINT] = _pinned_cross_fingerprint(row.chain_variant)

        rows.append(data)
    return rows


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
