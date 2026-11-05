"""The manifest and the models must agree.

A column is exported unless the manifest says, in writing, why it is not. These
tests fail when a model gains a table or a column that nobody decided about,
which is what let the export quietly lose MFA secrets, HSM links and OAuth2
credentials for several releases.
"""
import importlib

import pytest

from models import db
from services.backup import manifest


def _model_of(section):
    module_name, class_name = section.model.split(':')
    return getattr(importlib.import_module(module_name), class_name)


@pytest.fixture(scope='module')
def registered_tables(app):
    with app.app_context():
        import services.database_admin.helpers as helpers
        helpers._force_register_all_models()
        return set(db.metadata.tables)


class TestEveryTableIsDecidedAbout:
    def test_no_table_is_silently_absent(self, app, registered_tables):
        with app.app_context():
            exported = set()
            for name, section in manifest.SECTIONS.items():
                exported.add(_model_of(section).__tablename__)

            undecided = sorted(
                registered_tables - exported - set(manifest.EXCLUDED_TABLES))
            assert not undecided, (
                "these tables are neither exported nor excluded on purpose: "
                + ", ".join(undecided))

    def test_exclusions_carry_a_reason(self):
        for table, reason in manifest.EXCLUDED_TABLES.items():
            assert reason and len(reason) > 10, f"{table} is excluded without a reason"

    def test_excluded_tables_still_exist(self, registered_tables):
        stale = sorted(set(manifest.EXCLUDED_TABLES) - registered_tables
                       - {'schema_migrations', 'alembic_version'})
        assert not stale, f"the manifest excludes tables that are gone: {stale}"


class TestEveryColumnIsDecidedAbout:
    def test_no_column_is_silently_absent(self, app):
        with app.app_context():
            problems = []
            for name, section in manifest.SECTIONS.items():
                model = _model_of(section)
                columns = {c.key for c in model.__table__.columns}
                undecided = columns - set(section.exclude) - set(section.handled)
                # every remaining column is exported by construction; what we
                # check here is that the exclusions name real columns
                unknown = (set(section.exclude) | set(section.handled)) - columns
                if unknown:
                    problems.append(f"{name}: excludes unknown columns {sorted(unknown)}")
                if not undecided:
                    problems.append(f"{name}: excludes every column")
            assert not problems, "; ".join(problems)

    def test_exclusions_carry_a_reason(self):
        for name, section in manifest.SECTIONS.items():
            for column, reason in section.exclude.items():
                assert reason and len(reason) > 10, \
                    f"{name}.{column} is excluded without a reason"

    def test_handled_columns_name_where_they_are_written(self):
        for name, section in manifest.SECTIONS.items():
            assert not section.handled or section.custom, \
                f"{name} declares handled columns but has no dedicated exporter"
            for column, written_as in section.handled.items():
                assert written_as, f"{name}.{column} says nothing about where it goes"

    def test_identities_are_real_columns_and_never_only_the_surrogate_key(self, app):
        with app.app_context():
            for name, section in manifest.SECTIONS.items():
                model = _model_of(section)
                columns = {c.key for c in model.__table__.columns}
                assert section.identity, f"{name} has no stable identity"
                unknown = set(section.identity) - columns
                assert not unknown, f"{name}: identity names unknown columns {sorted(unknown)}"
                if section.identity == ('id',):
                    # Only singleton configuration rows may be identified by id
                    assert name in {'smtp_config', 'ad_connector'}, \
                        f"{name} identifies rows by primary key alone"

    def test_secrets_and_references_name_real_columns(self, app):
        with app.app_context():
            for name, section in manifest.SECTIONS.items():
                model = _model_of(section)
                columns = {c.key for c in model.__table__.columns}
                # secrets may be declared under the property name (totp_secret)
                # or the stored column (_credentials)
                for secret in section.secrets:
                    assert secret in columns or f'_{secret}' in columns, \
                        f"{name}: secret {secret!r} is not a column"
                for column, target in section.references.items():
                    assert column in columns, f"{name}: reference {column!r} is not a column"
                    assert target in manifest.SECTIONS, \
                        f"{name}.{column} points at unknown section {target!r}"

# Plain columns the application reads in the clear, and the reason each one
# is not something a restore should encrypt. A secret that is neither a
# property nor named in `Section.stored` has to be named here, on purpose:
# the alternative is the restore guessing, which is how the ACME account key,
# the deployment SSH key, the SCEP challenge, the Intune client secret and
# the webhook signing secret all came back readable in the database.
READ_IN_THE_CLEAR = {
    ('users', 'totp_secret'):
        "handed straight to pyotp, which cannot verify a ciphertext",
    ('users', 'backup_codes'):
        "Argon2id hashes, not encryption: they are already one-way",
}


class TestEverySecretSaysHowItGoesBack:
    """`secrets` says a column leaves the installation in the clear, so an
    archive can be restored on a server with another key. It said nothing
    about the way back, and the restore wrote the cleartext into the column:
    an installation that restored its own archive came out with its secrets
    readable in the database, and nothing said so."""

    def test_a_plain_column_names_its_layer_or_says_why_it_has_none(self, app):
        with app.app_context():
            undecided = []
            for name, section in manifest.SECTIONS.items():
                model = _model_of(section)
                for secret in section.secrets:
                    if isinstance(getattr(model, secret, None), property):
                        continue        # the setter re-encrypts
                    if secret in section.stored:
                        continue        # the layer is named
                    if (name, secret) in READ_IN_THE_CLEAR:
                        continue        # the reason is written down
                    undecided.append(f'{name}.{secret}')
            assert not undecided, (
                'these secrets are plain columns and nothing says whether a '
                f'restore should encrypt them: {sorted(undecided)}')

    def test_a_layer_is_one_this_version_writes(self):
        for name, section in manifest.SECTIONS.items():
            for column, layer in section.stored.items():
                assert column in section.secrets, (
                    f'{name}.{column} says how it is stored but is not a secret')
                assert layer in ('master', 'database', 'fields'), (
                    f'{name}.{column} names the layer {layer!r}, which is not '
                    'one this version writes')

    def test_a_property_does_not_also_name_a_layer(self, app):
        """Both would encrypt: the helper first, the setter over it."""
        with app.app_context():
            twice = []
            for name, section in manifest.SECTIONS.items():
                model = _model_of(section)
                for column in section.stored:
                    if isinstance(getattr(model, column, None), property):
                        twice.append(f'{name}.{column}')
            assert not twice, (
                f'these are properties and name a layer as well: {sorted(twice)}')

    def test_the_reasons_given_still_name_a_secret(self):
        """A reason written for a column that is no longer a secret is a
        reason nobody will re-read."""
        declared = {(name, secret) for name, section in manifest.SECTIONS.items()
                    for secret in section.secrets}
        stale = set(READ_IN_THE_CLEAR) - declared
        assert not stale, f'these reasons no longer name a secret: {sorted(stale)}'

class TestEveryForeignKeyIsDecidedAbout:
    """A numeric foreign key the manifest says nothing about is the source's
    own number, written straight into the target.

    Eight of them were: the authority signing an ACME zone, the group owning
    an SSH certificate, the certificate an ACME order renews and the one it
    reuses a key from, the role a custom role inherits, the certificate and
    the request of a Microsoft CA record, the account that created an HSM
    provider. Each landed on whatever row happened to hold that number here,
    and on PostgreSQL, where the column is enforced, the insert took the
    whole restore with it.

    The same rule as the rest of this file: a column is carried properly
    unless someone wrote down why it is not.
    """

    def test_no_integer_foreign_key_is_left_undeclared(self, app):
        from sqlalchemy import Integer

        with app.app_context():
            undeclared = []
            for name, section in manifest.SECTIONS.items():
                model = _model_of(section)
                for column in model.__table__.columns:
                    if not column.foreign_keys:
                        continue
                    if not isinstance(column.type, Integer):
                        continue        # an identifier that reads the same
                        # on every installation, such as an ACME account id
                    if column.key in section.references:
                        continue
                    if column.key in section.exclude:
                        continue
                    undeclared.append(f'{name}.{column.key}')
            assert not undeclared, (
                'these columns hold the number a row happens to have on the '
                'installation the archive came from, and the manifest neither '
                'resolves them nor says why it does not: '
                f'{sorted(undeclared)}')

    def test_a_reference_points_at_the_section_its_foreign_key_names(self, app):
        """A reference resolved against the wrong section resolves to
        nothing, or worse to the row of another table that shares a number."""
        with app.app_context():
            table_of = {}
            for name, section in manifest.SECTIONS.items():
                table_of[_model_of(section).__table__.name] = name

            wrong = []
            for name, section in manifest.SECTIONS.items():
                model = _model_of(section)
                columns = {c.key: c for c in model.__table__.columns}
                for column_name, target in section.references.items():
                    column = columns.get(column_name)
                    if column is None or not column.foreign_keys:
                        continue        # a reference over a column with no
                        # declared foreign key: nothing to compare it to
                    points_at = next(iter(column.foreign_keys)).column.table.name
                    named = table_of.get(points_at)
                    if named is not None and named != target:
                        wrong.append(
                            f'{name}.{column_name} is declared against '
                            f'{target!r} and its foreign key names {named!r}')
            assert not wrong, wrong

