"""Every column an archive carries comes back on another installation.

`test_backup_contract_matrix.py` proves each column reaches the archive. The
restore was the gap: hand-written restorers set the columns they named, so a
row came back with today's `created_at`, without its `updated_at` or its
description. One row is seeded in every section, every column given a value,
archived, restored onto an empty installation under other keys, and both
archives are compared column by column.
"""
import datetime
import uuid

import pytest
from sqlalchemy import inspect as sa_inspect

from models import Certificate, RevokedSerial, db
from services.backup import manifest
from services.backup.export_generic import REFERENCE_SUFFIX
from tests.test_backup_contract_matrix import _seed_all, _value_for
from tests.test_backup_cross_installation import PASSWORD, Keys, _installation, _service
from tests.test_restore_replace_dependents import _authority_row, _certificate_row

# {(section, column): reason} -- carried, and not put back as the archive has it
NOT_RESTORED_AS_ARCHIVED = {
    ('certificate_authorities', 'private_key_pem_encrypted'):
        "sealed under each archive's own salt and nonce: never the same bytes twice",
    ('certificates', 'private_key_pem_encrypted'):
        "sealed under each archive's own salt and nonce: never the same bytes twice",
}

# {(section, column): exception} -- columns whose model refuses a generic value.
# Empty today: every nullable column takes one, and a new refusal must be written here.
UNFILLABLE: dict = {}

_STAMP = datetime.datetime(2025, 3, 4, 5, 6, 7)


def _fill_nullable(rows):
    """A value in every empty column the restore could drop without anyone noticing.

    Returns the `(section, column)` the model refused the value for."""
    index, refused = 1000, {}
    for name, row in rows.items():
        section = manifest.SECTIONS[name]
        for column in sa_inspect(type(row)).local_table.columns:
            if (column.primary_key or column.foreign_keys or column.name in section.exclude
                    or column.name in section.secrets or column.name in section.references):
                continue
            attribute = sa_inspect(type(row)).get_property_by_column(column).key
            declared = str(column.type).upper()
            if 'DATETIME' in declared or 'TIMESTAMP' in declared:
                value = _STAMP      # a moment no restore would produce
            elif getattr(row, attribute) is None:
                index += 1
                value = _value_for(column, index)
            else:
                continue
            try:
                with db.session.begin_nested():
                    setattr(row, attribute, value)
                    db.session.flush()
            except Exception as exc:
                refused[(name, column.name)] = type(exc).__name__
    db.session.commit()
    return refused


def _key(name, row):
    """A row's identity, references spelled by the identity they carry."""
    section = manifest.SECTIONS[name]
    return tuple(str(row.get(f'{field}{REFERENCE_SUFFIX}') if field in section.references
                     else row.get(field)) for field in section.identity)


def _comparable(name, row):
    section = manifest.SECTIONS[name]
    return {column: value for column, value in row.items()
            if column != 'id' and column not in section.references
            and not (column.startswith('_') and not column.endswith(REFERENCE_SUFFIX))}


@pytest.fixture(scope='module')
def both_archives(app, tmp_path_factory):
    include = {name: True for name in manifest.SECTIONS}
    directory = tmp_path_factory.mktemp('column-coverage')
    with _installation(app, f"sqlite:///{directory / 'source.db'}", Keys(directory, 'source')), \
            app.app_context():
        issuer = _authority_row(f'coverage-ca-{uuid.uuid4().hex[:6]}')
        leaf = _certificate_row(f'coverage-leaf-{uuid.uuid4().hex[:6]}', issuer)
        # Custom sections the factory leaves to fixtures
        db.session.add(RevokedSerial(caref=issuer[0].refid, serial_number=leaf.serial_number,
                                     revoked_at=_STAMP, revoke_reason='keyCompromise',
                                     invalidity_at=_STAMP, valid_to=_STAMP, certificate_id=leaf.id,
                                     public_key_sha256='ab' * 32))
        db.session.commit()
        rows, _failures, _order, _secrets = _seed_all()
        refused = _fill_nullable(rows)
        # A request on a certificate the archive carries, or the restore cancels it
        leaf = db.session.query(Certificate).one()
        rows['key_recovery_requests'].cert_id = leaf.id
        rows['key_recovery_requests'].cert_refid = leaf.refid
        db.session.commit()
        svc = _service()
        blob = svc.create_backup(PASSWORD, include=include)
        _key_, archived = svc._decrypt_framed(blob, PASSWORD)
    with _installation(app, f"sqlite:///{directory / 'target.db'}", Keys(directory, 'target')), \
            app.app_context():
        svc = _service()
        svc.restore_backup(blob, PASSWORD, mode='merge')
        _key_, restored = svc._decrypt_framed(svc.create_backup(PASSWORD, include=include), PASSWORD)
    return archived, restored, refused


def test_every_carried_column_comes_back(both_archives):
    archived, restored, _refused = both_archives
    gaps = {}
    for name in sorted(manifest.SECTIONS):
        if not isinstance(archived.get(name), list):
            continue
        back = {_key(name, row): _comparable(name, row) for row in restored.get(name) or []}
        for row in archived[name]:
            here = back.get(_key(name, row))
            if here is None:
                gaps.setdefault(name, []).append('the row itself')
                continue
            for column, value in _comparable(name, row).items():
                if (name, column) in NOT_RESTORED_AS_ARCHIVED:
                    continue
                if here.get(column) != value:
                    gaps.setdefault(name, []).append(column)
    assert gaps == {}, f'carried and not restored as archived: {gaps}'


def test_nearly_every_section_is_exercised(both_archives):
    archived, _restored, _refused = both_archives
    empty = sorted(name for name in manifest.SECTIONS
                   if isinstance(archived.get(name), list) and not archived[name])
    # An SSH authority needs a real key pair, and its certificates hang off it
    assert empty == ['ssh_cas', 'ssh_certificates'], f'sections seeded with no row: {empty}'


def test_every_exemption_is_still_needed_and_explained(both_archives):
    archived, restored, _refused = both_archives
    for (name, column), reason in NOT_RESTORED_AS_ARCHIVED.items():
        assert reason.strip()
        back = {_key(name, row): row.get(column) for row in restored[name]}
        assert any(back.get(_key(name, row)) != row.get(column) for row in archived[name]), \
            f'{name}.{column} now comes back as archived: drop its exemption'



def test_a_column_left_empty_is_one_written_down(both_archives):
    """A column the seeder could not fill is a column the comparison cannot see."""
    _archived, _restored, refused = both_archives
    assert refused == UNFILLABLE, f'columns the seeder could not fill: {refused}'
