"""A restore of an old archive never reads a migration file.

The repairs of the 2.x migrations live in the restore code: with the migration
directory empty and unimportable, every one of them still runs (SQLite and PostgreSQL).
"""
import importlib
import pkgutil
import sys
from datetime import timedelta

import pytest
from sqlalchemy import text

from models import db
from tests.test_backup_acme_orders_and_requests import _orders, _order
from tests.test_restore_recorded_revocations import (  # noqa: F401  (fixture)
    TestAnOlderArchiveLeavesItsLiftedHoldsOut as LiftedHolds, _state as _hold_state,
)
from tests.test_restore_repairs import REPAIRED, _archive, _seed, _state
from tests.test_restore_replace_dependents import (  # noqa: F401  (fixture)
    PASSWORD, _authority_row, _certificate_row, _restore, _service, _snapshot, _user, target,
)
from utils.datetime_utils import utc_now

FOREIGN_ID = 7000


class _NoMigrations:
    """Meta path finder that refuses the `migrations` package, as an installation without it."""

    def find_spec(self, name, path=None, target=None):
        if name == 'migrations' or name.startswith('migrations.'):
            raise ModuleNotFoundError(f"No module named '{name}'", name=name)
        return None


@pytest.fixture
def no_migration_files(tmp_path, monkeypatch):
    import migration_runner
    empty = tmp_path / 'no-migrations'
    empty.mkdir()
    monkeypatch.setattr(migration_runner, 'MIGRATIONS_DIR', empty)
    for name in [n for n in sys.modules if n == 'migrations' or n.startswith('migrations.')]:
        monkeypatch.delitem(sys.modules, name)
    finder = _NoMigrations()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)


def test_the_production_modules_import_without_the_migrations(no_migration_files):
    import api
    import models
    import services
    import utils
    for package in (api, models, services, utils):
        for module in pkgutil.walk_packages(package.__path__, f'{package.__name__}.'):
            importlib.import_module(module.name)


def test_the_repairs_of_an_older_archive_run_without_the_migrations(target, no_migration_files):
    _seed()
    results = _service().restore_backup(_archive(older=True), PASSWORD, mode='merge')
    db.session.expire_all()
    assert all(_state()[key] == value for key, value in REPAIRED.items())
    assert set(results['repairs']) == set(REPAIRED)


def test_the_doubled_renewals_are_repaired_without_the_migrations(target, no_migration_files):
    _user('orders-admin')
    issuer = _authority_row('orders-ca')
    kept = _certificate_row('orders-kept', issuer)
    start = utc_now() - timedelta(days=60)
    _order(order_url='https://ca.example.test/order/o', certificate_id=kept.id,
           status='issued', renewal_enabled=True, last_renewal_at=start, created_at=start)
    _order(order_url='https://ca.example.test/order/o', certificate_id=kept.id,
           status='issued', created_at=start + timedelta(days=1))
    blob = _snapshot()
    for row in _orders():
        db.session.delete(row)
    db.session.commit()
    results = _restore(blob)
    assert [(o.order_url, o.status) for o in _orders()] == [('https://ca.example.test/order/o', 'issued')]
    assert results['acme_client_orders_repaired'] == {'reissued': 0, 'dropped': 1}


def test_a_lifted_hold_is_left_out_without_the_migrations(target, no_migration_files):
    results = LiftedHolds()._one('nomig-leftover')
    assert _hold_state('nomig-leftover') == (False, None, [])
    assert results['lifted_holds_skipped'] == 1


def test_the_users_counter_moves_above_restored_ids_without_the_migrations(target, no_migration_files):
    from models import User
    db.session.execute(text(
        "INSERT INTO audit_logs (action, resource_type, resource_id, details, timestamp) "
        f"VALUES ('nomig-audit', 'user', '{FOREIGN_ID}', 'deleted elsewhere', '2026-01-01 00:00:00')"))
    blob = _snapshot('audit_logs')
    db.session.execute(text("DELETE FROM audit_logs WHERE action = 'nomig-audit'"))
    db.session.commit()
    _restore(blob, mode='merge')
    user = User(username='nomig-user', email='nomig@example.test', password_hash='x' * 32,
                role='viewer', active=True)
    db.session.add(user)
    db.session.commit()
    assert user.id > FOREIGN_ID
