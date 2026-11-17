"""The restore holds its own session to one transaction, never another thread's (PostgreSQL:
the other thread commits while the restore's transaction is open)."""
import threading
import time

import pytest

from config.settings import Config
from models import db
from services import cluster_commands as cc
from services import cluster_maintenance as cm
from tests import pg_app_harness
from tests.test_cluster_maintenance_pg import (  # noqa: F401  (cluster: fixture)
    PREFIX, _add_user, _archive, _restore, _row, _sql, _user_exists, cluster, wait_for,
)

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')


def test_another_thread_commits_while_a_restore_runs(app, auth_client, monkeypatch):
    """Single node: only the restore's own session is one transaction; a commit made by
    another session meanwhile stays a commit. The restore's write gate refuses an ordinary
    write, so the neighbour writes as the restore's own bookkeeping does (exempt)."""
    monkeypatch.setattr(Config, 'HA_MODE', False)
    blob = _archive(app)
    from models import SystemConfig
    from services.backup.restore_core import RestoreCoreMixin
    real = RestoreCoreMixin._apply_all
    key = PREFIX + 'meanwhile'

    def with_a_neighbour(self, *args, **kwargs):
        real(self, *args, **kwargs)

        from services.cluster_maintenance import MaintenanceActive, exempt

        def neighbour():
            with app.app_context():
                try:
                    db.session.add(SystemConfig(key=key + '.refused', value='refused'))
                    db.session.commit()
                except MaintenanceActive:
                    db.session.rollback()
                with exempt():
                    db.session.add(SystemConfig(key=key, value='kept'))
                    db.session.commit()
        thread = threading.Thread(target=neighbour)
        thread.start()
        thread.join(10)
    monkeypatch.setattr(RestoreCoreMixin, '_apply_all', with_a_neighbour)
    try:
        r = _restore(auth_client, blob)
        assert r.status_code == 200, r.data
        assert _sql(app, "SELECT value FROM system_config WHERE key = :k", {'k': key}) == [('kept',)]
        assert _sql(app, "SELECT value FROM system_config WHERE key = :k",
                    {'k': key + '.refused'}) == []
        assert _sql(app, "SELECT count(*) FROM cluster_maintenance")[0][0] == 0
    finally:
        _sql(app, "DELETE FROM system_config WHERE key LIKE :k", {'k': key + '%'})
