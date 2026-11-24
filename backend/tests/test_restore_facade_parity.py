"""The two ways of asking for a restore must refuse the same things.

A restore rewrites the whole database, which is the largest concurrent write
a backend migration could be reading through, and an instance that has
written a new backend's configuration but not yet restarted onto it is still
running on the one it is leaving. The system route refuses both cases: it
takes the migration lock, and it declines while a switch is pending.

The settings route did neither, so which of the two an operator reached
decided whether their restore could land in the middle of a migration, or
onto a backend the next restart throws away.

The settings route always replaces, as its own docstring says. What it must
not do is accept a `mode` and ignore it: the same request then merged an
archive into a live instance from one page and overwrote the whole database
from the other, with nothing said either way.
"""
import io

import pytest

from tests.restore_support import post_to_the_end


def _upload(client, route, payload=b'not a real archive'):
    return post_to_the_end(
        client, route,
        data={'file': (io.BytesIO(payload), 'x.ucmbkp'),
              'password': 'a-password-that-is-long-enough'},
        content_type='multipart/form-data')


ROUTES = ('/api/v2/system/restore', '/api/v2/settings/backup/restore')


class TestASwitchThatHasNotHappenedYetHoldsBothRoutes:
    @pytest.mark.parametrize('route', ROUTES)
    def test_a_pending_switch_refuses_the_restore(self, app, auth_client,
                                                  monkeypatch, route):
        import importlib

        refusal = 'A backend switch is written and waiting for a restart.'
        patched = 0
        for module in ('api.v2.system.backup', 'api.v2.settings.backup'):
            loaded = importlib.import_module(module)
            if hasattr(loaded, 'pending_switch_refusal'):
                monkeypatch.setattr(loaded, 'pending_switch_refusal',
                                    lambda: refusal)
                patched += 1
        assert patched, (
            f'{route} does not even ask whether a switch is pending')

        response = _upload(auth_client, route)

        assert response.status_code == 409, (
            f'{route} answered {response.status_code}: a restore landing now '
            'is thrown away by the restart the switch is waiting for')


class TestAMigrationHoldsBothRoutes:
    @pytest.mark.parametrize('route', ROUTES)
    def test_a_busy_lock_refuses_the_restore(self, app, auth_client,
                                             monkeypatch, route):
        from services.database_admin.lock import MigrationBusyError

        def busy(*args, **kwargs):
            raise MigrationBusyError('A migration is running.')

        # At its source: the restore job takes the lock for both routes
        monkeypatch.setattr('services.database_admin.lock.database_migration_lock', busy)

        response = _upload(auth_client, route)

        assert response.status_code == 409, (
            f'{route} answered {response.status_code}: the restore ran while '
            'a migration was reading the database it rewrites')


class TestAModeThatIsNotHonouredIsRefused:
    def test_the_settings_route_refuses_merge(self, app, auth_client):
        response = post_to_the_end(
            auth_client, '/api/v2/settings/backup/restore',
            data={'file': (io.BytesIO(b'not a real archive'), 'x.ucmbkp'),
                  'password': 'a-password-that-is-long-enough',
                  'mode': 'merge'},
            content_type='multipart/form-data')

        assert response.status_code == 400, (
            f'the route answered {response.status_code} for a mode it does '
            'not honour: the caller believes their archive was merged and it '
            'replaced the instance')
        assert b'merge' in response.data.lower(), (
            'the refusal must point at the route that does honour it')

    def test_the_system_route_still_honours_merge(self, app, auth_client):
        """The other direction: refusing everywhere would be just as wrong."""
        response = post_to_the_end(
            auth_client, '/api/v2/system/restore',
            data={'file': (io.BytesIO(b'not a real archive'), 'x.ucmbkp'),
                  'password': 'a-password-that-is-long-enough',
                  'mode': 'merge'},
            content_type='multipart/form-data')

        # The archive is nonsense, so the answer is a refusal about the file,
        # never about the mode.
        assert response.status_code != 400 or b'always replaces' not in \
            response.data.lower()


class TestAnArchiveThatCarriesNothingChangesNothing:
    """An archive holding only its own metadata restores no row.

    Answering it as a success is wrong twice over: it revokes every session
    that was open, the caller's included, and asks for a restart, for a file
    that changed nothing. The system route has refused it since the backup
    campaign; the settings route went on revoking and announcing.
    """

    @pytest.mark.parametrize('route', ROUTES)
    def test_no_session_is_revoked_for_an_empty_archive(
            self, app, auth_client, monkeypatch, route):
        revoked = []

        # The class at its source: the routes hand the upload to the restore job
        from services.backup_service import BackupService
        monkeypatch.setattr(BackupService, 'restore_backup',
                            lambda self, *a, **k: {'sections_carried': []})

        import services.backup.restore.invalidate as invalidate
        monkeypatch.setattr(invalidate, 'invalidate_after_restore',
                            lambda *a, **k: revoked.append('revoked'))
        from tests.restore_job_support import sessions_kept
        sessions_kept(monkeypatch)  # the restore job's own sessions step

        response = _upload(auth_client, route)

        assert response.status_code == 200, response.data
        assert revoked == [], (
            f'{route} revoked every session for an archive that carried no '
            'data')
        assert b'no data' in response.data.lower(), (
            f'{route} announced a restore for a file that changed nothing')


class TestBothRoutesSayWhatTheArchiveGotWrong:
    """Two warnings the backup campaign added, and only one route carried.

    A record whose stored private key is not its certificate's signs
    certificates nobody can verify; the archive records that when it is
    written, deliberately, because a backup has to stay possible precisely
    when something is wrong. And an archive from a newer version may carry
    sections this one does not apply. Both must reach the operator whichever
    page they used.
    """

    @pytest.mark.parametrize('route', ROUTES)
    def test_a_key_that_cannot_sign_is_named(self, app, auth_client,
                                             monkeypatch, route):
        results = {
            'sections_carried': ['certificate_authorities'],
            'key_mismatches': ['certificate authority Root CA'],
            'sections_not_restored': ['something_newer'],
        }
        # The class at its source: the routes hand the upload to the restore job
        from services.backup_service import BackupService
        monkeypatch.setattr(BackupService, 'restore_backup',
                            lambda self, *a, **k: dict(results))

        import services.backup.restore.invalidate as invalidate
        monkeypatch.setattr(invalidate, 'invalidate_after_restore',
                            lambda *a, **k: None)
        from tests.restore_job_support import sessions_kept
        sessions_kept(monkeypatch)  # the restore job's own sessions step

        response = _upload(auth_client, route)
        body = response.data.lower()

        assert b'root ca' in body, (
            f'{route} did not say that a record carries a key that cannot '
            'sign: the operator hears it from the first client that refuses '
            'the chain instead')
        assert b'something_newer' in body, (
            f'{route} did not say the archive holds sections this version '
            'does not restore')


class TestAnUploadLeavesATrace:
    """Even an archive that restored nothing was uploaded.

    The empty-archive refusal returned before the audit entry on one route
    and after it on the other, so the same file left a line in the trail or
    did not, depending on which page it was dropped on. Introduced by a
    commit whose subject was parity.
    """

    @pytest.mark.parametrize('route', ROUTES)
    def test_an_empty_archive_is_still_recorded(self, app, auth_client,
                                                monkeypatch, route):
        recorded = []

        # The class at its source: the routes hand the upload to the restore job
        from services.backup_service import BackupService
        monkeypatch.setattr(BackupService, 'restore_backup',
                            lambda self, *a, **k: {'sections_carried': []})

        from services.audit_service import AuditService
        monkeypatch.setattr(
            AuditService, 'log_action',
            staticmethod(lambda **kw: recorded.append(kw.get('action'))))

        response = post_to_the_end(
            auth_client, route, data={'file': (io.BytesIO(b'x'), 'x.ucmbkp'),
                                      'password': 'a-password-long-enough'},
            content_type='multipart/form-data')

        # The archive must reach the restore, or the line below is the
        # refusal's own and proves nothing about an empty archive
        assert b'no data' in response.data.lower(), response.data

        assert 'system_restore' in recorded, (
            f'{route} left no trace of an archive that was uploaded')


class TestTheTwoMessagesReadTheSame:
    def test_neither_ends_with_two_full_stops(self):
        from services.backup.restore_report import with_restore_warnings

        results = {'key_mismatches': ['CA x']}
        for base in ('Backup restored successfully. Sign in again',
                     'Backup restored successfully. Every session opened '
                     'before the restore was revoked; restart the application '
                     'and sign in again.'):
            assert '..' not in with_restore_warnings(base, results)
