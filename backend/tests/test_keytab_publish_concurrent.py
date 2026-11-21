"""Two keytab uploads on two profiles at once: the stored file composes both.

Each upload recomposes the node file from the profiles. The second one must compose after
the first has committed, or its file lacks the first upload's keys. PostgreSQL only: SQLite
serializes the two writers instead.
"""
import os
import threading
import time
import uuid
from contextlib import contextmanager

import pytest

from models import SharedFile, WindowsEnrollmentProfile, db
from services import shared_files, windows_profiles
from services.kerberos import keytab_format
from tests.keytab_support import keytab
from tests.test_backup_cross_installation import _bound_to
from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
HOLD_SECONDS = 1.0
HOST = 'ucm.example.test'
ONE_2 = keytab((f'HTTP/{HOST}@ONE.TEST', 2))
ONE_3 = keytab((f'HTTP/{HOST}@ONE.TEST', 3))
TWO = keytab((f'HTTP/{HOST}@TWO.TEST', 2))

pytestmark = [pytest.mark.postgres, pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]


@contextmanager
def _database(app):
    # One schema per run: xdist workers share the database
    with _a_schema_of_our_own(f'keytab_publish_race_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        yield


@pytest.fixture(params=['file stored', 'no file yet'])
def profiles(app, request):
    """Profile ONE.TEST (default) and TWO.TEST; with 'file stored', ONE holds kvno 2 and the
    node file composes it."""
    with _database(app), app.app_context():
        one = WindowsEnrollmentProfile(name='default', is_default=True, enabled=True, realm='ONE.TEST')
        two = WindowsEnrollmentProfile(name='two', enabled=True, realm='TWO.TEST')
        db.session.add_all([one, two])
        if request.param == 'file stored':
            one.set_keytab(ONE_2)
            db.session.flush()
            windows_profiles.publish_keytab()
        db.session.commit()
        ids = (one.id, two.id)
        db.session.remove()
        yield ids


def _realms(data):
    return sorted((e.realm, e.kvno) for e in keytab_format.read_entries(data))


def test_the_second_upload_composes_the_first_one_s_keys(app, profiles):
    one_id, two_id = profiles
    published, errors = threading.Event(), []

    def upload(profile_id, data, hold):
        try:
            with app.app_context():
                profile = db.session.get(WindowsEnrollmentProfile, profile_id)
                profile.set_keytab(data)
                if not hold:
                    published.wait(5)
                windows_profiles.publish_keytab(actor='race')
                if hold:
                    published.set()
                    time.sleep(HOLD_SECONDS)
                db.session.commit()
                db.session.remove()
        except Exception as e:  # reported below, a thread swallows it otherwise
            errors.append(e)
            published.set()

    threads = [threading.Thread(target=upload, args=(one_id, ONE_3, True)),
               threading.Thread(target=upload, args=(two_id, TWO, False))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(15)

    assert errors == []
    with app.app_context():
        stored = shared_files.read_file(shared_files.KERBEROS_KEYTAB)
        assert _realms(stored) == [('ONE.TEST', 3), ('TWO.TEST', 2)]
        assert stored == windows_profiles.composed_keytab()
        assert SharedFile.query.count() == 1
        db.session.remove()


THREE = keytab((f'HTTP/{HOST}@THREE.TEST', 2))


@pytest.mark.parametrize('uploaded, expected', [
    ('two', [('ONE.TEST', 2), ('THREE.TEST', 2), ('TWO.TEST', 2)]),
    ('default', [('ONE.TEST', 3), ('THREE.TEST', 2)]),
], ids=['new realm', 'replaced keytab'])
def test_a_start_racing_an_upload_keeps_the_upload(app, monkeypatch, tmp_path, uploaded, expected):
    """A stored file the profiles do not compose is rebuilt at start: it must compose after
    the concurrent upload commits, from the profiles as committed then."""
    from config.settings import Config
    from services.kerberos import negotiate_auth
    monkeypatch.setattr(Config, 'HA_MODE', False)
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', tmp_path / 'kerberos.keytab')
    with _database(app):
        with app.app_context():
            one = WindowsEnrollmentProfile(name='default', is_default=True, enabled=True, realm='ONE.TEST')
            two = WindowsEnrollmentProfile(name='two', enabled=True, realm='TWO.TEST')
            three = WindowsEnrollmentProfile(name='three', enabled=True, realm='THREE.TEST')
            db.session.add_all([one, two, three])
            one.set_keytab(ONE_2)
            three.set_keytab(THREE)
            # Stale stored file: THREE's keys are missing from it
            shared_files.store_file(shared_files.KERBEROS_KEYTAB, ONE_2)
            db.session.commit()
            target_id, data = (two.id, TWO) if uploaded == 'two' else (one.id, ONE_3)
            db.session.remove()

        published, errors = threading.Event(), []

        def upload():
            try:
                with app.app_context():
                    db.session.get(WindowsEnrollmentProfile, target_id).set_keytab(data)
                    windows_profiles.publish_keytab(actor='race')
                    published.set()
                    time.sleep(HOLD_SECONDS)
                    db.session.commit()
                    db.session.remove()
            except Exception as e:  # reported below, a thread swallows it otherwise
                errors.append(e)
                published.set()

        def start():
            try:
                published.wait(5)
                negotiate_auth.restore_keytab_at_start(app)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=upload), threading.Thread(target=start)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(15)

        assert errors == []
        with app.app_context():
            stored = shared_files.read_file(shared_files.KERBEROS_KEYTAB)
            assert _realms(stored) == expected
            assert stored == windows_profiles.composed_keytab()
            db.session.remove()
