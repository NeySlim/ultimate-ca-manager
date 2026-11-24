"""conftest's per-module clean-up of ACME accounts: a module's own accounts leave with it,
the others stay, and a refusal or an absent database is never an error of the next module.
The CI runs UCM_TEST_LEAK_MODE=warn, where a broken clean-up shows nowhere else."""
import uuid
import warnings

import pytest

from models import db
from models.acme_models import AcmeAccount
from tests import acme_accounts_support, conftest
from tests.acme_accounts_support import account_ids


def _account(tag):
    with conftest._SESSION_APP[0].app_context():
        row = AcmeAccount(account_id=f'leave-{tag}-{uuid.uuid4().hex[:8]}', jwk='{}',
                          jwk_thumbprint=f'leave-{uuid.uuid4().hex}')
        db.session.add(row)
        db.session.commit()
        return row.account_id


def _remove(app, *ids):
    with app.app_context():
        AcmeAccount.query.filter(AcmeAccount.account_id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


class _Request:
    fspath = 'test_some_module.py'


def _the_module_fixture():
    return conftest._shared_tables_stay_in_their_module._get_wrapped_function()


def test_the_fixture_removes_the_accounts_a_module_created_and_keeps_the_others(app):
    old = _account('old')
    module = _the_module_fixture()(_Request())
    next(module)
    new = _account('new')
    try:
        with pytest.raises(StopIteration):
            next(module)
        ids = account_ids(app)
        assert new not in ids
        assert old in ids
    finally:
        _remove(app, old, new)


def test_a_module_without_a_database_snapshot_removes_nothing(app):
    new = _account('unsnapshotted')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            conftest._drop_new_acme_accounts(None)
        assert new in account_ids(app)
    finally:
        _remove(app, new)


def test_a_removal_that_fails_warns_and_never_raises(app, monkeypatch):
    new = _account('refused')

    def refuse(app_, kept):
        raise RuntimeError('database is locked')
    monkeypatch.setattr(acme_accounts_support, 'drop_accounts_but', refuse)
    try:
        with pytest.warns(UserWarning, match='ACME accounts of this file not removed: RuntimeError'):
            conftest._drop_new_acme_accounts(set())
        assert new in account_ids(app)
    finally:
        _remove(app, new)


def test_the_snapshot_is_the_accounts_there_are_and_none_without_a_session_app(app, monkeypatch):
    kept = _account('snapshot')
    try:
        assert kept in conftest._acme_account_ids()
        monkeypatch.setattr(conftest, '_SESSION_APP', [])
        assert conftest._acme_account_ids() is None
    finally:
        monkeypatch.undo()
        _remove(app, kept)


def test_the_snapshot_is_none_when_the_accounts_cannot_be_read(app, monkeypatch):
    def unreadable(app_):
        raise RuntimeError('no such table: acme_accounts')
    monkeypatch.setattr(acme_accounts_support, 'account_ids', unreadable)
    assert conftest._acme_account_ids() is None
