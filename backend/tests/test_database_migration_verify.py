"""Tests for the post-copy verification of a backend migration.

Each test builds a target the way a migration leaves one — a temporary SQLite
file carrying the whole UCM schema through ``db.metadata.create_all`` — and
then either populates it correctly or breaks it the way a copy breaks things:
a table short of rows, an orphan inserted with foreign keys off, a value in an
encrypted column that no longer decrypts.
"""
import base64
import json
import os
import tempfile

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect, text

from services.database_admin import verify as verify_mod
from services.database_admin.verify import (
    VerificationError,
    check_local_email_flags,
    check_foreign_keys,
    check_row_counts,
    check_schema,
    check_secret_decryption,
    check_sequences,
    check_unique_constraints,
    verify_migration,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def target(app):
    """An empty SQLite target carrying the full schema, as a migration builds it."""
    from services.database_admin.helpers import _force_register_all_models
    from models import db

    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    _force_register_all_models()
    engine = create_engine(f'sqlite:///{path}')
    db.metadata.create_all(engine)

    yield engine

    engine.dispose()
    if os.path.exists(path):
        os.unlink(path)


def _add_user(engine, user_id, username, *, email=None, sso=False,
              totp_secret=None):
    """Insert one user row directly, the way the bulk loader does."""
    with engine.begin() as conn:
        conn.execute(
            text('INSERT INTO users (id, username, email, password_hash, role, '
                 'has_sso_identity, totp_secret) VALUES (:id, :username, :email, '
                 ':password_hash, :role, :sso, :totp_secret)'),
            {
                'id': user_id,
                'username': username,
                'email': email or f'{username}@example.test',
                'password_hash': 'not-a-real-hash',
                'role': 'viewer',
                'sso': sso,
                'totp_secret': totp_secret,
            },
        )


PARTIAL = 'uq_windows_enrollment_profiles_default'


def _add_profile(engine, profile_id, *, is_default=False):
    """One Windows enrolment profile: at most one is the default (a partial unique index)."""
    with engine.begin() as conn:
        conn.execute(
            text('INSERT INTO windows_enrollment_profiles (id, name, is_default, enabled, '
                 'policy_id, policy_oid_root, validity_days) VALUES (:id, :name, :is_default, 1, '
                 ':policy, :oid, 365)'),
            {'id': profile_id, 'name': f'profile-{profile_id}', 'is_default': is_default,
             'policy': f'policy-{profile_id}', 'oid': f'1.2.3.{profile_id}'})


def _populate(engine):
    """A small, consistent target: two users, one group, one membership."""
    _add_user(engine, 1, 'admin', totp_secret='JBSWY3DPEHPK3PXP')
    _add_user(engine, 2, 'alice')
    with engine.begin() as conn:
        conn.execute(text('INSERT INTO groups (id, name) VALUES (1, :name)'),
                     {'name': 'operators'})
        conn.execute(text('INSERT INTO group_members (id, group_id, user_id) '
                          'VALUES (1, 1, 1)'))
    return {'users': 2, 'groups': 1, 'group_members': 1}


def _set_totp_secret(engine, user_id, value):
    with engine.begin() as conn:
        conn.execute(text('UPDATE users SET totp_secret = :value WHERE id = :id'),
                     {'value': value, 'id': user_id})


class _InspectorWithExtras:
    """The real inspector, plus one constraint the target does not declare.

    SQLite cannot hold data that violates a unique index it declares — it
    refuses the INSERT — so the state this check exists to catch (rows that
    reached a PostgreSQL target before its index, or under a collation the two
    backends spell differently) cannot be built inside a SQLite file. Only the
    declaration is simulated here: the GROUP BY still runs against the real
    rows of the real target.
    """

    def __init__(self, real, table, *, constraints=(), indexes=()):
        self._real = real
        self._table = table
        self._constraints = list(constraints)
        self._indexes = list(indexes)

    def __getattr__(self, name):
        return getattr(self._real, name)

    def get_unique_constraints(self, table_name, **kwargs):
        found = list(self._real.get_unique_constraints(table_name, **kwargs))
        if table_name == self._table:
            found.extend(self._constraints)
        return found

    def get_indexes(self, table_name, **kwargs):
        found = list(self._real.get_indexes(table_name, **kwargs))
        if table_name == self._table:
            found.extend(self._indexes)
        return found


# ---------------------------------------------------------------------------
# The whole report
# ---------------------------------------------------------------------------

class TestVerifyMigration:

    def test_correct_target_passes_every_check(self, target):
        counts = _populate(target)

        report = verify_migration(target, counts, target_is_pg=False)

        assert report['ok'] is True
        assert report['target_backend'] == 'sqlite'
        assert set(report['checks']) == {
            'schema', 'row_counts', 'foreign_keys', 'unique_constraints',
            'local_email_flags', 'sequences', 'secrets',
        }
        assert report['checks']['row_counts']['rows'] == 4
        assert report['checks']['foreign_keys']['constraints_checked'] > 0

    def test_report_is_json_serialisable(self, target):
        counts = _populate(target)

        report = verify_migration(target, counts, target_is_pg=False)

        # The API hands this dict to the operator and the audit log stores it.
        assert json.loads(json.dumps(report))['ok'] is True

    def test_report_carries_no_connection_string(self, target):
        counts = _populate(target)

        serialised = json.dumps(verify_migration(target, counts, target_is_pg=False))

        assert 'sqlite:///' not in serialised
        assert tempfile.gettempdir() not in serialised

    def test_verifying_the_wrong_backend_is_refused(self, target):
        # A clean report about a database nobody is switching to is worse
        # than no report at all.
        with pytest.raises(VerificationError) as excinfo:
            verify_migration(target, {}, target_is_pg=True)

        assert 'PostgreSQL' in str(excinfo.value)

    def test_first_failing_check_stops_the_run(self, target):
        _populate(target)

        with pytest.raises(VerificationError):
            verify_migration(target, {'users': 99}, target_is_pg=False)


# ---------------------------------------------------------------------------
# 1. Row counts
# ---------------------------------------------------------------------------

class TestRowCounts:

    def test_matching_counts_pass(self, target):
        counts = _populate(target)

        result = check_row_counts(target, counts)

        assert result['per_table'] == counts
        assert result['rows'] == 4

    def test_mismatch_names_the_table_and_both_numbers(self, target):
        _populate(target)

        with pytest.raises(VerificationError) as excinfo:
            check_row_counts(target, {'users': 7})

        message = str(excinfo.value)
        assert 'users' in message
        assert '7' in message and '2' in message

    def test_unreadable_table_is_a_failure_not_a_skip(self, target):
        with pytest.raises(VerificationError) as excinfo:
            check_row_counts(target, {'no_such_table': 0})

        assert 'no_such_table' in str(excinfo.value)


# ---------------------------------------------------------------------------
# 2. Foreign keys
# ---------------------------------------------------------------------------

class TestForeignKeys:

    def test_consistent_target_passes(self, target):
        _populate(target)

        result = check_foreign_keys(target)

        assert result['orphans'] == 0
        assert result['constraints_checked'] > 0

    def test_orphan_row_is_detected(self, target):
        _populate(target)
        # SQLite enforces nothing here (the loader copies with
        # PRAGMA foreign_keys=OFF, and so does this insert).
        with target.begin() as conn:
            conn.execute(text('INSERT INTO group_members (id, group_id, user_id) '
                              'VALUES (2, 1, 4242)'))

        with pytest.raises(VerificationError) as excinfo:
            check_foreign_keys(target)

        message = str(excinfo.value)
        assert 'group_members' in message
        assert 'users' in message

    def test_composite_foreign_key_orphan_is_detected(self, target):
        # UCM declares no composite foreign key, so the pair is built here.
        with target.begin() as conn:
            conn.execute(text(
                'CREATE TABLE ucm_test_parent ('
                ' tenant_id INTEGER NOT NULL, code TEXT NOT NULL,'
                ' PRIMARY KEY (tenant_id, code))'))
            conn.execute(text(
                'CREATE TABLE ucm_test_child ('
                ' id INTEGER PRIMARY KEY, tenant_id INTEGER, code TEXT,'
                ' FOREIGN KEY (tenant_id, code)'
                ' REFERENCES ucm_test_parent (tenant_id, code))'))
            conn.execute(text("INSERT INTO ucm_test_parent VALUES (1, 'alpha')"))
            conn.execute(text("INSERT INTO ucm_test_child VALUES (1, 1, 'alpha')"))
            # A partly NULL composite key satisfies the constraint (MATCH
            # SIMPLE on both backends) and must not be reported.
            conn.execute(text("INSERT INTO ucm_test_child VALUES (2, NULL, 'alpha')"))

        assert check_foreign_keys(target)['composite_constraints'] == 1

        with target.begin() as conn:
            conn.execute(text("INSERT INTO ucm_test_child VALUES (3, 9, 'ghost')"))

        with pytest.raises(VerificationError) as excinfo:
            check_foreign_keys(target)

        message = str(excinfo.value)
        assert 'ucm_test_child' in message
        assert 'ucm_test_parent' in message

    def test_missing_parent_table_is_a_failure(self, target):
        with target.begin() as conn:
            conn.execute(text(
                'CREATE TABLE ucm_test_orphan_child ('
                ' id INTEGER PRIMARY KEY, parent_id INTEGER,'
                ' FOREIGN KEY (parent_id) REFERENCES ucm_test_absent (id))'))

        with pytest.raises(VerificationError) as excinfo:
            check_foreign_keys(target)

        assert 'ucm_test_absent' in str(excinfo.value)


# ---------------------------------------------------------------------------
# 3. Unique constraints and unique indexes
# ---------------------------------------------------------------------------

class TestUniqueConstraints:

    def test_clean_target_passes_and_reports_what_it_skipped(self, target):
        _populate(target)

        result = check_unique_constraints(target)

        assert result['duplicate_groups'] == 0
        assert result['constraints_checked'] > 0
        assert result['unique_indexes_checked'] > 0
        skipped = {entry['constraint'] for entry in result['skipped']}
        assert PARTIAL in skipped
        assert result['skipped_count'] == len(result['skipped'])
        assert all(entry['reason'] for entry in result['skipped'])

    def test_partial_unique_index_is_not_a_false_positive(self, target):
        # One default profile at most (a partial index): two profiles that are not
        # the default are legitimate and a global GROUP BY would wrongly condemn
        # the migration.
        _add_profile(target, 1)
        _add_profile(target, 2)

        result = check_unique_constraints(target)

        assert result['duplicate_groups'] == 0
        partial = [entry for entry in result['skipped']
                   if entry['constraint'] == PARTIAL]
        assert len(partial) == 1
        assert 'partial index' in partial[0]['reason']

    def test_duplicate_on_a_unique_constraint_is_detected(self, target, monkeypatch):
        _add_user(target, 1, 'local_user', email='shared@example.test')
        _add_user(target, 2, 'sso_user', email='shared@example.test', sso=True)

        monkeypatch.setattr(verify_mod, 'inspect', lambda engine: _InspectorWithExtras(
            sa_inspect(engine), 'users',
            constraints=[{'name': 'uq_users_email', 'column_names': ['email']}]))

        with pytest.raises(VerificationError) as excinfo:
            check_unique_constraints(target)

        message = str(excinfo.value)
        assert 'uq_users_email' in message
        assert 'users' in message

    def test_duplicate_on_a_unique_index_is_detected(self, target, monkeypatch):
        _add_user(target, 1, 'local_user', email='shared@example.test')
        _add_user(target, 2, 'sso_user', email='shared@example.test', sso=True)

        monkeypatch.setattr(verify_mod, 'inspect', lambda engine: _InspectorWithExtras(
            sa_inspect(engine), 'users',
            indexes=[{'name': 'ix_users_email_total', 'column_names': ['email'],
                      'unique': 1, 'dialect_options': {}}]))

        with pytest.raises(VerificationError) as excinfo:
            check_unique_constraints(target)

        assert 'ix_users_email_total' in str(excinfo.value)

    def test_null_values_are_not_duplicates(self, target, monkeypatch):
        # Both backends treat NULL as distinct for uniqueness; GROUP BY does not.
        _add_user(target, 1, 'one', totp_secret=None)
        _add_user(target, 2, 'two', totp_secret=None)

        monkeypatch.setattr(verify_mod, 'inspect', lambda engine: _InspectorWithExtras(
            sa_inspect(engine), 'users',
            indexes=[{'name': 'ix_users_totp', 'column_names': ['totp_secret'],
                      'unique': 1, 'dialect_options': {}}]))

        assert check_unique_constraints(target)['duplicate_groups'] == 0


class TestLocalEmailFlags:
    """has_sso_identity, which the local e-mail index reads, agrees with the identity rows."""

    def test_agreeing_flags_pass(self, target):
        _add_user(target, 1, 'local_user', email='shared@example.test')
        _add_user(target, 2, 'sso_user', email='shared@example.test', sso=True)
        with target.begin() as conn:
            conn.execute(text("INSERT INTO user_sso_identities (user_id, orphan_of) "
                              "VALUES (2, 'oauth2:https://idp.example')"))
        assert check_local_email_flags(target)['accounts_checked'] == 2

    def test_a_flag_without_its_row_is_refused(self, target):
        # Out of the index, this account could share the e-mail of a local one unnoticed
        _add_user(target, 1, 'flagged', sso=True)
        with pytest.raises(VerificationError) as excinfo:
            check_local_email_flags(target)
        assert 'has_sso_identity' in str(excinfo.value)

    def test_a_row_without_its_flag_is_refused(self, target):
        _add_user(target, 1, 'unflagged')
        with target.begin() as conn:
            conn.execute(text("INSERT INTO user_sso_identities (user_id, orphan_of) "
                              "VALUES (1, 'oauth2:https://idp.example')"))
        with pytest.raises(VerificationError):
            check_local_email_flags(target)


# ---------------------------------------------------------------------------
# 4. Sequences
# ---------------------------------------------------------------------------

class TestSequences:

    def test_sqlite_reports_not_applicable_without_raising(self, target):
        result = check_sequences(target)

        assert result['applicable'] is False
        assert result['backend'] == 'sqlite'
        assert result['sequences_checked'] == 0
        assert 'not applicable' in result['reason']


# ---------------------------------------------------------------------------
# 5. Schema
# ---------------------------------------------------------------------------

class TestSchema:

    def test_complete_target_passes(self, target):
        result = check_schema(target)

        assert result['tables_expected'] == result['tables_present']
        assert result['columns_checked'] > 0

    def test_missing_table_is_reported(self, target):
        with target.begin() as conn:
            conn.execute(text('DROP TABLE acme_nonces'))

        with pytest.raises(VerificationError) as excinfo:
            check_schema(target)

        assert 'acme_nonces' in str(excinfo.value)

    def test_missing_column_is_reported(self, target):
        with target.begin() as conn:
            conn.execute(text('ALTER TABLE users DROP COLUMN full_name'))

        with pytest.raises(VerificationError) as excinfo:
            check_schema(target)

        assert 'users.full_name' in str(excinfo.value)


# ---------------------------------------------------------------------------
# 6. Encrypted columns
# ---------------------------------------------------------------------------

class TestSecretDecryption:

    def test_readable_values_pass(self, target):
        _populate(target)

        result = check_secret_decryption(target)

        assert result['columns_checked'] > 0
        assert result['per_column']['users.totp_secret']['sampled'] == 1

    def test_every_declared_secret_column_is_covered(self, target):
        columns = verify_mod.encrypted_columns()

        # The manifest is the authority, plus the private keys it carries
        # under another name.
        assert ('users', 'totp_secret') in columns
        assert ('certificate_authorities', 'prv') in columns
        assert ('certificates', 'prv') in columns
        assert ('pro_sso_providers', 'oauth2_client_secret') in columns
        assert ('smtp_config', 'smtp_password') in columns

    def test_encrypted_value_is_read_back(self, target, encryption_enabled):
        from security.encryption import encrypt_text

        stored = encrypt_text('JBSWY3DPEHPK3PXP')
        assert stored != 'JBSWY3DPEHPK3PXP'
        _add_user(target, 1, 'admin', totp_secret=stored)

        result = check_secret_decryption(target)

        assert result['per_column']['users.totp_secret']['decrypted'] == 1

    def test_undecryptable_value_fails_without_echoing_it(self, target):
        _add_user(target, 1, 'admin')
        # An 'ENC:' payload that is not a valid token: what a copy that
        # re-encoded the column leaves behind.
        corrupted = base64.b64encode(b'ENC:' + b'gAAAAA-truncated-token').decode()
        _set_totp_secret(target, 1, corrupted)

        with pytest.raises(VerificationError) as excinfo:
            check_secret_decryption(target)

        message = str(excinfo.value)
        assert 'users.totp_secret' in message
        assert corrupted not in message
        assert 'truncated-token' not in message

    def test_bytes_that_are_no_longer_text_fail(self, target):
        _add_user(target, 1, 'admin')
        _set_totp_secret(target, 1, b'\x89\xff\x00secret-bytes')

        with pytest.raises(VerificationError) as excinfo:
            check_secret_decryption(target)

        message = str(excinfo.value)
        assert 'users.totp_secret' in message
        assert 'secret-bytes' not in message

    def test_null_and_empty_values_do_not_fail(self, target):
        _add_user(target, 1, 'admin', totp_secret=None)
        _add_user(target, 2, 'alice', totp_secret='')
        _add_user(target, 3, 'bob', totp_secret='   ')

        result = check_secret_decryption(target)

        stats = result['per_column']['users.totp_secret']
        assert stats['empty'] == 2  # the NULL row is not even sampled
        assert result['values_sampled'] == 2

    def test_missing_secret_column_is_a_failure(self, target):
        with target.begin() as conn:
            conn.execute(text('ALTER TABLE users DROP COLUMN totp_secret'))

        with pytest.raises(VerificationError) as excinfo:
            check_secret_decryption(target)

        assert 'users.totp_secret' in str(excinfo.value)
