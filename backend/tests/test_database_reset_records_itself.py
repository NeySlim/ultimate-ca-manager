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
            assert str(path) in answer.get_json()['data']['read_command']
        assert answer.get_json()['data']['password_generated'] is (initial is None)
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


def test_a_reset_whose_drop_fails_keeps_the_live_password_file(app, auth_client, monkeypatch, tmp_path):
    """The generated file is written once the tables are recreated, never over a live one before."""
    from auth.initial_admin import PASSWORD_FILE_NAME
    monkeypatch.setitem(app.config, 'INITIAL_ADMIN_PASSWORD', None)
    monkeypatch.setitem(app.config, 'INITIAL_ADMIN_PASSWORD_FILE', None)
    monkeypatch.setitem(app.config, 'DATA_DIR', str(tmp_path))
    path = tmp_path / PASSWORD_FILE_NAME
    path.write_text('Live-Generated-Value-7\n')
    with app.app_context():
        holder = User(username='reset-file-holder', email='h@example.test', role='admin', active=True)
        holder.set_password('Live-Generated-Value-7')
        db.session.add(holder)
        db.session.commit()

    def failing_drop(*a, **k):
        raise RuntimeError('drop refused')
    monkeypatch.setattr(db, 'drop_all', failing_drop)
    try:
        answer = auth_client.post('/api/v2/system/database/reset')
        assert answer.status_code >= 400
        assert path.read_text() == 'Live-Generated-Value-7\n'
        with app.app_context():
            held = User.query.filter_by(username='reset-file-holder').one()
            assert held.check_password(path.read_text().rstrip('\n'))
    finally:
        with app.app_context():
            User.query.filter_by(username='reset-file-holder').delete()
            db.session.commit()


def test_a_reset_whose_file_cannot_be_written_says_so(app, auth_client, monkeypatch, tmp_path):
    from auth import initial_admin
    monkeypatch.setitem(app.config, 'INITIAL_ADMIN_PASSWORD', None)
    monkeypatch.setitem(app.config, 'INITIAL_ADMIN_PASSWORD_FILE', None)
    monkeypatch.setitem(app.config, 'DATA_DIR', str(tmp_path))

    def full_disk(path, value):
        raise OSError(28, 'No space left on device')
    monkeypatch.setattr(initial_admin, '_write_atomically', full_disk)
    answer = auth_client.post('/api/v2/system/database/reset')
    assert answer.status_code == 500 and 'not created' in answer.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(username=app.config['INITIAL_ADMIN_USERNAME']).count() == 0
        assert AuditLog.query.filter_by(action='database_reset', success=False).count() == 1
        # Later tests sign in as admin with the test password
        initial_admin.seed_admin(app.config, initial_admin.InitialPassword('changeme123', False, 'test'))
        db.session.commit()


@pytest.mark.parametrize('ha', [True, False], ids=['ha', 'single'])
def test_a_reset_in_ha_names_the_node_holding_the_file(app, auth_client, monkeypatch, tmp_path, caplog, ha):
    from auth.initial_admin import PASSWORD_FILE_NAME
    from config.settings import Config
    monkeypatch.setitem(app.config, 'INITIAL_ADMIN_PASSWORD', None)
    monkeypatch.setitem(app.config, 'INITIAL_ADMIN_PASSWORD_FILE', None)
    monkeypatch.setitem(app.config, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(Config, 'HA_MODE', ha)
    monkeypatch.setattr(Config, 'NODE_ID', 'reset-node-7')
    with caplog.at_level('INFO', logger='api.v2.system.database'):
        answer = auth_client.post('/api/v2/system/database/reset')
    assert answer.status_code == 200, answer.data
    with app.app_context():
        # Later tests sign in as admin with the test password, no change forced
        admin = User.query.filter_by(username=app.config['INITIAL_ADMIN_USERNAME']).one()
        value = (tmp_path / PASSWORD_FILE_NAME).read_text().rstrip('\n')
        admin.set_password('changeme123')
        admin.force_password_change = False
        db.session.commit()
    body = answer.get_json()
    assert value not in caplog.text and value not in answer.get_data(as_text=True)
    if ha:
        assert body['data']['node'] == 'reset-node-7' and 'reset-node-7' in body['message']
        assert 'reset-node-7' in caplog.text
    else:
        assert body['data']['node'] is None
