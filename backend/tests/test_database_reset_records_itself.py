"""A database reset leaves a record of itself, in the database it recreates.

The route imported a function that does not exist, so it answered 500 and
reset nothing on every call. Made to work again, it then had a subtler
problem: the entry was written after `drop_all` and `create_all`, which is
the only place it can survive, but it was attributed by looking the actor up
on `g.current_user`. That instance is expired by then and its row has just
been destroyed, so the lookup raised, `log_action` swallowed it and wrote
nothing, and the route still answered "Database reset successfully".

It looked right in testing only because the administrator running the reset
is usually the one the reset recreates, who comes back with the same row.
"""
import pytest

from models import db, AuditLog, User


@pytest.fixture(autouse=True, scope='module')
def _startup_data_back_after_the_resets(app):
    """The resets drop what the application seeds at startup (system templates,
    roles): seeding again leaves later files the database they would start with."""
    yield
    from app import init_database
    with app.app_context():
        db.session.rollback()
        init_database(app)


class TestTheResetIsRecorded:
    def test_an_administrator_who_is_not_the_bootstrap_one_is_named(
            self, app, auth_client):
        """The case the identifier coincidence used to hide."""
        with app.app_context():
            other = User(username='reset-probe-admin',
                         email='reset-probe@example.test',
                         role='admin', active=True, totp_exempt=True)
            other.set_password('Sup3rSecret!2026')
            db.session.add(other)
            db.session.commit()

        client = auth_client.application.test_client()
        signed_in = client.post('/api/v2/auth/login',
                                json={'username': 'reset-probe-admin',
                                      'password': 'Sup3rSecret!2026'})
        assert signed_in.status_code == 200, signed_in.data

        answer = client.post('/api/v2/system/database/reset')
        assert answer.status_code == 200, answer.data

        with app.app_context():
            recorded = AuditLog.query.filter_by(action='database_reset').all()
            assert recorded, (
                'the reset answered successfully and recorded nothing, in a '
                'table it had just recreated for the purpose')
            assert recorded[0].username == 'reset-probe-admin', (
                'the entry does not name who asked for the reset: '
                f'{recorded[0].username}')
            assert recorded[0].success is True

    def test_the_entry_is_the_first_row_of_the_new_table(
            self, app, auth_client):
        """Written before the drop it went into the table that was about to
        be destroyed, so a reset left no trace at all."""
        answer = auth_client.post('/api/v2/system/database/reset')
        assert answer.status_code == 200, answer.data

        with app.app_context():
            rows = AuditLog.query.order_by(AuditLog.id).all()
            assert rows, 'the ledger is empty after the reset'
            assert rows[0].action == 'database_reset', (
                f'the first row of the recreated table is {rows[0].action}')
            # Sealed like any other entry: a chain that restarts is still a
            # chain, and this is its genesis.
            assert rows[0].entry_hash, 'the entry was not sealed'


@pytest.mark.parametrize('initial', ['Operator-Chosen-1!', None], ids=['provided', 'generated'])
def test_the_recreated_admin_is_forced_only_with_a_generated_password(
        app, auth_client, monkeypatch, tmp_path, initial):
    from auth.initial_admin import PASSWORD_FILE_NAME
    monkeypatch.setitem(app.config, 'INITIAL_ADMIN_PASSWORD', initial)
    monkeypatch.setitem(app.config, 'DATA_DIR', str(tmp_path))
    answer = auth_client.post('/api/v2/system/database/reset')
    assert answer.status_code == 200, answer.data
    path = tmp_path / PASSWORD_FILE_NAME
    with app.app_context():
        admin = User.query.filter_by(username=app.config['INITIAL_ADMIN_USERNAME']).one()
        assert admin.force_password_change is (initial is None)
        assert path.exists() is (initial is None)
        if initial is None:
            value = path.read_text().rstrip('\n')
            assert admin.check_password(value)
            assert value not in answer.get_data(as_text=True)
            assert str(path) in answer.get_data(as_text=True)
        # Later files sign in as admin with the test password, no change forced
        admin.set_password('changeme123')
        admin.force_password_change = False
        db.session.commit()
    assert not path.exists()


def test_an_unreadable_password_file_resets_nothing(app, auth_client, monkeypatch, tmp_path):
    monkeypatch.setitem(app.config, 'INITIAL_ADMIN_PASSWORD', None)
    monkeypatch.setitem(app.config, 'INITIAL_ADMIN_PASSWORD_FILE', str(tmp_path / 'missing'))
    with app.app_context():
        probe = User(username='reset-survivor', email='s@example.test', role='viewer', active=True)
        probe.set_password('Surv1vor-Pass!')
        db.session.add(probe)
        db.session.commit()
    try:
        answer = auth_client.post('/api/v2/system/database/reset')
        assert answer.status_code == 409 and 'INITIAL_ADMIN_PASSWORD_FILE' in answer.get_data(as_text=True)
        with app.app_context():
            assert User.query.filter_by(username='reset-survivor').count() == 1
    finally:
        with app.app_context():
            User.query.filter_by(username='reset-survivor').delete()
            db.session.commit()
