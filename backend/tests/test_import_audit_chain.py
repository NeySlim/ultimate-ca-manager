"""Entries written by the bundle import are sealed like every other.

The importer stages its audit entries rather than writing them through
`AuditService.log_action`, and that part is right: `log_action` commits the
session it is given, and the import is one transaction on purpose.

What it did not do was seal them. `prev_hash` and `entry_hash` were left
empty, so the chain restarted from its genesis at every imported object, and
`verify_integrity` walked across the break and reported a valid ledger. An
entry inserted or altered between two unsealed rows would not have been
noticed.
"""
import pytest

from models import db, AuditLog


class TestTheImportEntriesAreSealed:
    def _stage_one(self, app, name):
        from services.smart_import.importer import SmartImporter

        with app.app_context():
            importer = SmartImporter()
            importer._log_audit('import_certificate', 4242, name, 'tester')
            importer._stage_audit()
            db.session.commit()
            return AuditLog.query.filter_by(resource_name=name).first()

    def test_the_entry_carries_a_hash_and_its_predecessor(self, app):
        entry = self._stage_one(app, 'import-chain-probe')
        assert entry is not None, 'the entry was not staged at all'
        assert entry.entry_hash, 'the entry is not sealed'
        assert entry.prev_hash, 'the entry does not name its predecessor'

    def test_the_chain_is_continuous_across_it(self, app):
        """The row before it must be the one it names."""
        with app.app_context():
            anchor = AuditLog.query.order_by(AuditLog.id.desc()).first()
            expected = anchor.entry_hash if anchor else '0' * 64

        entry = self._stage_one(app, 'import-chain-continuity')
        assert entry.prev_hash == expected, (
            'the chain restarts at this entry instead of continuing: it '
            f'names {entry.prev_hash[:12]} where the row before it seals to '
            f'{expected[:12]}')

    def test_the_integrity_check_would_see_a_break(self, app):
        """A sealed chain is one the verification can actually walk."""
        self._stage_one(app, 'import-chain-verified')
        with app.app_context():
            from services.audit_service import AuditService
            report = AuditService.verify_integrity()
            assert report['valid'], (
                f'the ledger does not verify: {report.get("errors")}')
            assert report['checked'] > 0


def test_the_import_stages_its_entries_after_its_own_writes(app, monkeypatch):
    """Appending to the chain locks it until the commit: an import that staged
    an entry per object held that lock across its later writes, and a writer
    holding a row it needed waited on the lock in turn."""
    from sqlalchemy import event
    from services.audit import staging
    from services.smart_import.importer import SmartImporter
    from tests.test_smart_import_duplicate import _make_cert

    order = []
    real_append = staging.append_entry
    monkeypatch.setattr(staging, 'append_entry',
                        lambda entry, **kw: order.append('audit') or real_append(entry, **kw))

    def before_flush(session, _context, _instances):
        if any(not isinstance(o, AuditLog) for o in list(session.new) + list(session.dirty)):
            order.append('write')

    content = _make_cert('import-order-a', 'CN=Import Order Issuer A', 7001) + \
        _make_cert('import-order-b', 'CN=Import Order Issuer B', 7002)
    with app.app_context():
        session = db.session()
        commit = lambda _session: order.append('commit')   # noqa: E731
        event.listen(session, 'before_flush', before_flush)
        event.listen(session, 'after_commit', commit)
        try:
            result = SmartImporter().execute(content, username='tester')
        finally:
            event.remove(session, 'before_flush', before_flush)
            event.remove(session, 'after_commit', commit)
    assert result.success, result.errors
    # What follows the commit (webhook deliveries) is a transaction of its own
    import_transaction = order[:order.index('commit')]
    assert import_transaction.count('audit') >= 2, order
    assert 'write' not in import_transaction[import_transaction.index('audit'):], order
