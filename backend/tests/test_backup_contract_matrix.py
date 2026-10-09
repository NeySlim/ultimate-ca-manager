"""What a backup carries, checked section by section rather than by sample.

`tests/test_backup_manifest.py` compares the manifest to the models: it
catches a table or a column nobody decided about. What it cannot see is
whether the decision is honoured at run time, and the export tests that do
look at real archives look at a handful of sections chosen by hand.

This file closes that gap by seeding one row in *every* section the manifest
declares, from the models themselves, and then checking the four promises the
manifest makes about each of them:

  * the section is in the archive;
  * every column it declares is in the row, unless it is excluded with a
    reason or handled under another name;
  * every column it declares as a secret travels readable, since the archive
    has to be restorable on an installation with a different database key;
  * every relation it declares travels with the identity of the row it points
    at, not only with a primary key that means nothing elsewhere.

The rows are built generically: required columns are filled by type, required
foreign keys are resolved against a row seeded earlier. A section the factory
cannot build is named in :data:`UNSEEDABLE` with the reason, the same rule
the manifest itself follows, so a new section that nothing can exercise fails
the suite rather than quietly leaving a hole.
"""
import datetime
import json

import pytest
from sqlalchemy import inspect as sa_inspect

from models import db
from services.backup import manifest
from services.backup.export_generic import load_model

PASSWORD = 'Correct-Horse-Battery-9'

# Rows this file creates are recognisable, so the teardown removes exactly
# what it added and nothing the rest of the suite is looking at.
MARK = 'zzcontract'

# {section: reason} — sections that hang off one the factory does not build,
# because its exporter reads real cryptographic material nothing can invent.
# Whether they seed depends on what the rest of the suite left in the shared
# database, so they are allowed to be absent, never to be absent silently:
# an entry is a decision, with a reason someone can check.
NEEDS_REAL_MATERIAL: dict = {
    'ssh_certificates': (
        'it hangs off an SSH authority, whose exporter reads a real key, and '
        'the suite has no SSH authority factory'
    ),
}

# How many passes the seeder makes over the sections it has not built yet.
# Each pass can only resolve a foreign key whose parent an earlier pass
# created, so the count bounds the depth of the dependency chain.
_SEEDING_PASSES = 6


def _value_for(column, index):
    """A plausible value for a required column, from its declared type."""
    declared = str(column.type).upper()
    if 'BOOL' in declared:
        return False
    if 'INT' in declared:
        return 1
    if 'FLOAT' in declared or 'NUMERIC' in declared or 'REAL' in declared:
        return 1.0
    if 'DATETIME' in declared or 'TIMESTAMP' in declared:
        return datetime.datetime(2026, 1, 1, 0, 0, 0)
    if 'DATE' in declared:
        return datetime.date(2026, 1, 1)
    if 'BLOB' in declared or 'BINARY' in declared:
        return b'contract'
    if 'JSON' in declared:
        return {}
    return f'{MARK}-{index}'


def _is_ours(row) -> bool:
    """Whether this archived row is one this file seeded."""
    return any(isinstance(value, str) and value.startswith(MARK)
               for value in row.values())


def _fill_secrets(name, row):
    """Put a real, encrypted value in every column the manifest calls a secret.

    Left empty, those columns are never exercised: the seeder only fills what
    the schema requires, and a secret is almost always nullable. The value
    goes through the model's own attribute, so whatever setter encrypts it in
    production encrypts it here, and the export is then asked the question it
    exists to answer -- does this leave the installation readable?
    """
    section = manifest.SECTIONS[name]
    written = set()
    for column in section.secrets:
        try:
            with db.session.begin_nested():
                setattr(row, column, f'{MARK}-secret-{name}-{column}')
                db.session.flush()
        except Exception:
            # A column this version stores differently, or a setter that
            # refuses the shape: the section is still seeded, that secret is
            # simply not exercised. Which one it was is returned, because a
            # secret nobody wrote is a secret the archive cannot be asked
            # about -- and the table below would stay empty for the wrong
            # reason.
            continue
        written.add((name, column))
    return written


def _sections_by_table():
    """{table name: section name} for resolving a foreign key to a section."""
    mapping = {}
    for name, section in manifest.SECTIONS.items():
        mapping[sa_inspect(load_model(section)).local_table.name] = name
    return mapping


def _any_existing(section_name):
    """A row of that section already in the database, or None.

    The sections with a dedicated exporter hold real cryptographic material
    (a certificate, a private key), which no generic factory can invent: the
    fixtures create those, and a foreign key pointing at one is resolved
    against what is there rather than against something this file made up.
    """
    model = load_model(manifest.SECTIONS[section_name])
    return model.query.first()


def _seed_all():
    """Create one row per section; return (rows, failures, order, secrets)."""
    by_table = _sections_by_table()
    rows, failures, order, secrets_written = {}, {}, [], set()
    # Sections whose exporter reads real cryptographic material are left to
    # the fixtures: a row carrying "zzcontract-7" where a certificate belongs
    # aborts the export, which is the export doing its job.
    remaining = {name: section for name, section in manifest.SECTIONS.items()
                 if not section.custom}
    index = 0

    for _pass in range(_SEEDING_PASSES):
        # A parent this file created itself is used in preference to one the
        # rest of the suite left behind: reusing an existing pair is how a
        # membership hits the unique constraint it already satisfies. Rows
        # already in the database are a last resort, for the children of
        # sections the factory does not build.
        allow_existing = _pass >= _SEEDING_PASSES - 2
        for name in list(remaining):
            model = load_model(remaining[name])
            table = sa_inspect(model).local_table
            values, blocked = {}, None

            for column in table.columns:
                if column.primary_key or column.nullable:
                    continue
                if column.default is not None or column.server_default is not None:
                    continue
                if column.foreign_keys:
                    reference = list(column.foreign_keys)[0]
                    parent_section = by_table.get(reference.column.table.name)
                    parent = rows.get(parent_section)
                    if parent is None and parent_section and allow_existing:
                        parent = _any_existing(parent_section)
                    if parent is None:
                        blocked = (f'its {reference.column.table.name} parent '
                                   'has not been created yet')
                        break
                    values[column.name] = getattr(parent, reference.column.name)
                    continue
                index += 1
                values[column.name] = _value_for(column, index)

            if blocked:
                failures[name] = blocked
                continue

            try:
                # A savepoint per attempt: a plain rollback would undo every
                # row seeded since the last commit, so one section the factory
                # cannot build would silently empty the ones before it — and
                # leave them looking seeded to everything downstream.
                with db.session.begin_nested():
                    row = model(**values)
                    db.session.add(row)
                    db.session.flush()
            except Exception as exc:
                failures[name] = f'{type(exc).__name__}: {str(exc)[:120]}'
                continue

            table = sa_inspect(model).local_table
            secrets_written |= _fill_secrets(name, row)
            rows[name] = row
            order.append((name, {column.name: getattr(row, column.name)
                                 for column in table.primary_key.columns}))
            remaining.pop(name)
            failures.pop(name, None)

        if not remaining:
            break

    db.session.commit()
    return rows, failures, order, secrets_written


def _remove(order):
    """Delete the seeded rows by primary key, children before parents.

    By key rather than by a marker in a text column: several of these tables
    have no text column the factory fills, so a marker-based delete left their
    rows behind. On SQLite the next run then reuses the freed row ids of their
    parents and the leftovers collide with the new membership, which is how a
    leak turns into a failure in a file that has nothing to do with it.
    """
    for name, primary_key in reversed(order):
        model = load_model(manifest.SECTIONS[name])
        try:
            with db.session.begin_nested():
                model.query.filter_by(**primary_key).delete(
                    synchronize_session=False)
        except Exception:
            continue
    db.session.commit()


@pytest.fixture(scope='module')
def seeded(app, create_ca, create_cert):
    """One row in every section, and the archive taken while they are there.

    Built once for the module: every test below only reads it.

    The sections with a dedicated exporter read real cryptographic material,
    which no generic factory can invent, so the suite's own factories create
    those two and the rest is built from the models.
    """
    from services.backup_service import BackupService

    authority = create_ca(cn=f'{MARK}-contract-ca.test')
    create_cert(cn=f'{MARK}-contract-leaf.test', ca_id=authority['id'])

    with app.app_context():
        rows, failures, order, secrets_written = _seed_all()
        try:
            service = BackupService()
            # Everything, historical sections included: this file checks the
            # contract of the whole manifest, not of the default selection.
            blob = service.create_backup(
                PASSWORD,
                include={name: True for name in manifest.SECTIONS})
            _key, payload = service._decrypt_framed(blob, PASSWORD)
            yield {'payload': payload, 'failures': failures,
                   'seeded': set(rows), 'secrets_written': secrets_written}
        finally:
            _remove(order)


class TestEverySectionCanBeExercised:
    def test_the_factory_builds_a_row_for_every_section(self, seeded):
        """A section nothing can build is a section nothing below checks."""
        unexpected = {
            name: why for name, why in seeded['failures'].items()
            if name not in NEEDS_REAL_MATERIAL
        }

        assert unexpected == {}, (
            'these sections could not be seeded and are not written down in '
            f'NEEDS_REAL_MATERIAL: {unexpected}')

    def test_a_section_that_did_not_seed_was_only_blocked_by_a_parent(
            self, seeded):
        """The exemption is for a missing parent, not for a model that
        refuses the row: the second is a real gap and has to surface."""
        for name, why in seeded['failures'].items():
            assert 'has not been created yet' in why, (
                f'{name} did not seed for a reason the exemption does not '
                f'cover: {why}')

    def test_every_exempt_section_carries_a_reason(self, seeded):
        assert all(reason.strip() for reason in NEEDS_REAL_MATERIAL.values())

    def test_almost_everything_is_actually_exercised(self, seeded):
        """The file is worth its cost only while it covers nearly all of the
        manifest; a slow drift towards exemptions would empty it quietly."""
        assert len(seeded['seeded']) >= len(manifest.SECTIONS) - 6


class TestTheArchiveCarriesEverySection:
    def test_a_seeded_section_is_in_the_archive(self, app, seeded):
        missing = sorted(
            name for name in seeded['seeded']
            if not seeded['payload'].get(name))

        # The count in the database is part of the message: "the archive is
        # empty" and "the row was never there" are different failures.
        with app.app_context():
            held = {name: load_model(manifest.SECTIONS[name]).query.count()
                    for name in missing}

        assert missing == [], (
            'these sections hold a row and the archive carries none of them: '
            f'{held}')


class TestEveryDeclaredColumnTravels:
    def test_no_declared_column_is_absent_from_the_rows(self, seeded):
        """A column the manifest neither excludes nor hands to a dedicated
        exporter has to be in the archive: that is the whole rule."""
        gaps = {}

        for name in sorted(seeded['seeded']):
            section = manifest.SECTIONS[name]
            rows = seeded['payload'].get(name) or []
            if not rows:
                continue
            table = sa_inspect(load_model(section)).local_table
            carried = set(rows[0])
            expected = {
                column.name for column in table.columns
                if column.name not in section.exclude
                and column.name not in section.handled
            }
            absent = sorted(expected - carried)
            if absent:
                gaps[name] = absent

        assert gaps == {}, f'columns declared and not carried: {gaps}'


# {(section, column): reason} — secrets that still leave the installation as
# ciphertext, bound to the database key of the server that wrote the archive.
#
# Measured on values this file writes itself, through the model attribute the
# application uses. A column absent from this list can still travel encrypted
# when the value was stored by some other path: what is pinned here is the
# ordinary one.
# Each is a secret nobody can use on another installation, which is the whole
# point of decrypting them on the way out. Listed rather than ignored: the
# test below fails both when something new joins them and when one of them is
# fixed and left here.
KNOWN_TO_TRAVEL_ENCRYPTED: dict = {}


class TestEverySecretTravelsReadable:
    def test_a_declared_secret_is_not_ciphertext_in_the_archive(self, seeded):
        """Secrets are decrypted on the way out on purpose: an archive bound
        to the source's database key is an archive that only restores onto
        the installation that wrote it."""
        from security.encryption import key_encryption
        from utils.encryption import is_encrypted as is_db_encrypted

        still_encrypted = set()
        readable = set()

        for name in sorted(seeded['seeded']):
            section = manifest.SECTIONS[name]
            for column in section.secrets:
                for row in seeded['payload'].get(name) or []:
                    # Only the rows this file wrote: another file's row was
                    # stored by another path, and what it does on the way out
                    # is a different question from the one asked here.
                    if not _is_ours(row):
                        continue
                    value = row.get(column)
                    if not isinstance(value, str) or not value:
                        continue
                    expected = f'{MARK}-secret-{name}-{column}'
                    if value == expected:
                        readable.add((name, column))
                    elif (key_encryption.is_string_encrypted(value)
                            or is_db_encrypted(value)):
                        still_encrypted.add((name, column))

        unexpected = sorted(still_encrypted - set(KNOWN_TO_TRAVEL_ENCRYPTED))
        assert unexpected == [], (
            f'secrets left the installation as ciphertext: {unexpected}')

        if not key_encryption.is_enabled:
            # Nothing is stored encrypted on this installation, so nothing can
            # travel encrypted either: the debt below is about what happens
            # when at-rest encryption is on, and there is nothing to check.
            return

        # The other direction: a secret that is readable now and still listed
        # here hides the next one.
        fixed = sorted(
            entry for entry in KNOWN_TO_TRAVEL_ENCRYPTED
            if entry in readable and entry not in still_encrypted)
        assert fixed == [], (
            f'these secrets travel readable now: {fixed} -- take them out of '
            'KNOWN_TO_TRAVEL_ENCRYPTED')

    def test_the_debt_list_carries_a_reason(self):
        assert all(reason.strip()
                   for reason in KNOWN_TO_TRAVEL_ENCRYPTED.values())

    def test_every_declared_secret_was_actually_written(self, seeded):
        """An empty debt table means nothing if the column was never seeded.

        `_fill_secrets` lets a setter refuse a value and carries on, because
        a section that cannot take one shape of secret is still worth seeding
        for everything else. But a secret nobody wrote is a secret the
        archive was never asked about, and the list above then stays empty
        for the wrong reason.
        """
        expected = {(name, column) for name in seeded['seeded']
                    for column in manifest.SECTIONS[name].secrets}
        never_written = sorted(expected - seeded['secrets_written'])
        assert never_written == [], (
            'these secrets were seeded by nothing, so nothing above says '
            f'whether they leave the installation readable: {never_written}')


class TestEveryRelationTravelsByIdentity:
    def test_a_declared_reference_carries_the_identity_of_its_target(
            self, seeded):
        """A numeric key means nothing on another installation. Every
        relation is exported beside the identity of the row it points at."""
        from services.backup.export_generic import REFERENCE_SUFFIX

        missing = {}

        for name in sorted(seeded['seeded']):
            section = manifest.SECTIONS[name]
            for column, target in section.references.items():
                assert target in manifest.SECTIONS, (
                    f'{name}.{column} points at an unknown section {target!r}')
                for row in seeded['payload'].get(name) or []:
                    if row.get(column) is None:
                        continue
                    if column + REFERENCE_SUFFIX not in row:
                        missing.setdefault(name, []).append(column)

        assert missing == {}, (
            f'relations exported without the identity of their target: {missing}')


class TestTheArchiveAccountsForWhatItCarries:
    def test_every_seeded_section_is_counted_in_the_metadata(self, seeded):
        """The counts are what a restore checks the archive against before it
        writes anything; a section missing from them is unverifiable."""
        metadata = seeded['payload'].get('metadata') or {}
        sections = metadata.get('sections') or {}

        uncounted = sorted(
            name for name in seeded['seeded']
            if seeded['payload'].get(name) and name not in sections)

        assert uncounted == [], f'sections carried and not counted: {uncounted}'

    def test_the_archive_is_serialisable_as_it_is_read_back(self, seeded):
        json.dumps(seeded['payload'], default=str)
