"""Restore: what stays valid afterwards unless something invalidates it.

Each test here pins one half of the guarantee the restore needs once its
transaction has committed: no access granted before the restore survives it,
and no cache keeps answering with the state that was replaced -- while a
cache that refuses to be dropped stays a warning, never a failed restore.
"""
import pytest

from models import SSOSession, UserSession, User, db
from services.backup.restore import invalidate as invalidate_module
from services.backup.restore.invalidate import invalidate_after_restore
from tests.test_session_cleanup_task import sql_store  # noqa: F401 (fixture)


@pytest.fixture(autouse=True)
def session_store(app, tmp_path, monkeypatch):
    """Point the session store at a temporary directory.

    The function empties whatever directory is configured; tests must not be
    able to empty the session store of the machine running them.
    """
    store = tmp_path / 'sessions'
    store.mkdir()
    monkeypatch.setitem(app.config, 'SESSION_FILE_DIR', str(store))
    return store


@pytest.fixture
def user_id(app):
    """Any existing user: sessions reference one, the restore replaces them."""
    with app.app_context():
        user = User.query.filter_by(username='admin').first()
        assert user is not None
        return user.id


def _open_session(user_id, session_id):
    db.session.add(UserSession(user_id=user_id, session_id=session_id))
    db.session.commit()


class TestSessionsAreRevoked:
    """A session opened before the restore authenticates against identities
    the instance no longer has."""

    def test_open_sessions_are_deleted_and_counted(self, app, user_id):
        with app.app_context():
            _open_session(user_id, 'restore-invalidate-1')
            _open_session(user_id, 'restore-invalidate-2')
            assert UserSession.query.count() == 2

            result = invalidate_after_restore()

            assert result['sessions_revoked'] == 2
            assert UserSession.query.count() == 0

    def test_sso_sessions_are_deleted_too(self, app, user_id):
        with app.app_context():
            provider = db.session.execute(
                db.text("SELECT id FROM pro_sso_providers LIMIT 1")
            ).first()
            from models.sso import SSOProvider
            created = None
            if provider is None:
                created = SSOProvider(name='restore-invalidate-sso', provider_type='ldap')
                db.session.add(created)
                db.session.flush()
                provider = (created.id,)
            db.session.add(SSOSession(user_id=user_id, provider_id=provider[0],
                                      session_id='restore-invalidate-sso'))
            db.session.commit()
            try:
                result = invalidate_after_restore()

                assert result['sso_sessions_revoked'] >= 1
                assert SSOSession.query.count() == 0
            finally:
                db.session.rollback()
                if created is not None:
                    SSOSession.query.filter_by(provider_id=provider[0]).delete()
                    SSOProvider.query.filter_by(id=provider[0]).delete()
                    db.session.commit()

    def test_a_failed_revocation_raises_and_stops_everything(
            self, app, user_id, monkeypatch):
        """The point of the function: a surviving session is not a warning."""
        class Unreachable:
            __tablename__ = 'user_sessions'

            class query:
                @staticmethod
                def delete(*args, **kwargs):
                    raise RuntimeError('the session table is unreachable')

        restarts = []
        monkeypatch.setattr(invalidate_module, 'UserSession', Unreachable)
        monkeypatch.setattr('utils.service_manager.restart_service',
                            lambda: restarts.append(True) or (True, 'ok'))

        with app.app_context():
            with pytest.raises(RuntimeError):
                invalidate_after_restore(request_restart=True)

        assert restarts == [], "a restore that kept sessions must not look done"


class TestSessionFilesAreRemoved:
    """The database rows list the sessions; the files in the store are the
    sessions -- a file left behind is a cookie that still works."""

    def test_session_files_are_deleted_and_counted(self, app, user_id, session_store):
        (session_store / 'session_alpha').write_bytes(b'authenticated user id')
        (session_store / 'session_beta').write_bytes(b'authenticated user id')
        (session_store / 'subdir').mkdir()

        with app.app_context():
            result = invalidate_after_restore()

        assert result['session_files_removed'] == 2
        assert not (session_store / 'session_alpha').exists()
        assert not (session_store / 'session_beta').exists()
        assert (session_store / 'subdir').is_dir()

    def test_an_unknown_store_is_not_an_error(self, app, user_id, monkeypatch):
        monkeypatch.setitem(app.config, 'SESSION_FILE_DIR', None)

        with app.app_context():
            result = invalidate_after_restore()

        assert result['session_files_removed'] == 0
        assert result['caches_cleared']


class TestSqlSessionStoreIsEmptied:
    """With the SQL store the rows are the sessions: all of them die."""

    def test_flask_session_rows_are_deleted_and_counted(self, app, user_id, sql_store):
        with app.app_context():
            for sid in ('one', 'two', 'three'):
                db.session.execute(db.text(
                    "INSERT INTO flask_sessions (session_id, data, expiry) "
                    "VALUES (:s, :d, '2999-01-01')"), {'s': sid, 'd': b'x'})
            db.session.commit()

            result = invalidate_after_restore()

            assert result['flask_sessions_revoked'] == 3
            assert db.session.execute(db.text('SELECT COUNT(*) FROM flask_sessions')).scalar() == 0

    def test_other_stores_report_zero(self, app, user_id):
        with app.app_context():
            assert invalidate_after_restore()['flask_sessions_revoked'] == 0


class TestCachesArePurged:
    """A stale cache is a wrong answer with a bounded lifetime: worth
    dropping, never worth failing a committed restore for."""

    def test_the_known_caches_are_cleared(self, app, user_id):
        with app.app_context():
            result = invalidate_after_restore()

        for name in ('acme_proxy', 'external_crl_entries', 'ocsp_responses',
                     'oidc_discovery'):
            assert name in result['caches_cleared'], result
        assert result['caches_failed'] == []

    def test_a_purge_that_raises_does_not_stop_the_others(
            self, app, user_id, monkeypatch):
        def refuse():
            raise RuntimeError('this cache will not be dropped')

        monkeypatch.setattr('services.oidc_id_token.clear_oidc_cache', refuse)

        with app.app_context():
            result = invalidate_after_restore()

        assert 'oidc_discovery' not in result['caches_cleared']
        assert 'oidc_discovery' in result['caches_failed']
        assert 'acme_proxy' in result['caches_cleared']
        assert len(result['caches_cleared']) == len(invalidate_module.CACHE_PURGES) - 1

    def test_a_cache_whose_module_is_gone_is_reported_not_raised(
            self, app, user_id, monkeypatch):
        """An optional module that cannot even be imported fails alone."""
        def missing():
            raise ImportError("No module named 'services.kerberos'")

        monkeypatch.setattr(invalidate_module, 'CACHE_PURGES',
                            (('gone', missing),) + invalidate_module.CACHE_PURGES)

        with app.app_context():
            result = invalidate_after_restore()

        assert result['caches_failed'] == ['gone']
        assert 'acme_proxy' in result['caches_cleared']


class TestRestartIsCentralizedAndOptIn:
    """Only the caller knows whether the restore it just applied warrants
    cutting every live connection."""

    def test_no_restart_by_default(self, app, user_id, monkeypatch):
        restarts = []
        monkeypatch.setattr('utils.service_manager.restart_service',
                            lambda: restarts.append(True) or (True, 'ok'))

        with app.app_context():
            result = invalidate_after_restore()

        assert restarts == []
        assert result['restart_requested'] is False

    def test_restart_goes_through_the_centralized_mechanism(
            self, app, user_id, monkeypatch):
        restarts = []
        monkeypatch.setattr('utils.service_manager.restart_service',
                            lambda: restarts.append(True) or (True, 'restarting'))

        with app.app_context():
            result = invalidate_after_restore(request_restart=True)

        assert len(restarts) == 1
        assert result['restart_requested'] is True

    def test_a_refused_restart_is_reported_not_raised(
            self, app, user_id, monkeypatch):
        """The data is already restored; the caller must still hear about it,
        and be able to say a manual restart is needed."""
        monkeypatch.setattr('utils.service_manager.restart_service',
                            lambda: (False, 'signal file is not writable'))

        with app.app_context():
            result = invalidate_after_restore(request_restart=True)

        assert result['restart_requested'] is False
        assert result['caches_cleared']

    def test_a_raising_restart_is_reported_not_raised(
            self, app, user_id, monkeypatch):
        def boom():
            raise OSError('read-only file system')

        monkeypatch.setattr('utils.service_manager.restart_service', boom)

        with app.app_context():
            result = invalidate_after_restore(request_restart=True)

        assert result['restart_requested'] is False


def test_summary_line_reports_database_session_rows(app, user_id, sql_store, caplog):
    import logging
    with app.app_context():
        for sid in ('one', 'two', 'three'):
            db.session.execute(db.text(
                "INSERT INTO flask_sessions (session_id, data, expiry) "
                "VALUES (:s, :d, '2999-01-01')"), {'s': sid, 'd': b'x'})
        db.session.commit()
        with caplog.at_level(logging.INFO):
            invalidate_after_restore()
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith('Restore: revoked'))
    assert '3 database session rows' in line
