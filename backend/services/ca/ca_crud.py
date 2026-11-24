"""
CA CRUD operations
"""
import logging
from types import SimpleNamespace
from typing import List, Optional

from models import CA, Certificate, db
from services.audit_service import AuditService
from services.deletion_blockers import ca_deletion_blockers, first_blocker, purge_ca_dependents
from .helpers import delete_ca_files

logger = logging.getLogger(__name__)


class CAcrudMixin:
    """CA Create, Read, Update, Delete operations"""

    @staticmethod
    def get_ca(ca_id: int) -> Optional[CA]:
        """Get CA by ID"""
        return db.session.get(CA, ca_id)

    @staticmethod
    def get_ca_by_refid(refid: str) -> Optional[CA]:
        """Get CA by refid"""
        return CA.query.filter_by(refid=refid).first()

    @staticmethod
    def list_cas() -> List[CA]:
        """List all CAs, ordered by creation date descending"""
        return CA.query.order_by(CA.created_at.desc()).all()

    @staticmethod
    def delete_ca(ca_id: int, username: str = 'system') -> bool:
        """
        Delete a CA and its associated files.

        Args:
            ca_id: CA ID
            username: User deleting

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If CA is used by certificates or is parent of other CAs
        """
        ca = db.session.get(CA, ca_id)
        if not ca:
            return False

        # The same refusals as the routes, for any caller that skipped them
        blocker = first_blocker(ca_deletion_blockers(ca))
        if blocker:
            raise ValueError(blocker.message)

        # Snapshot for the webhook payload before the row is gone
        _ca_snapshot = ca.to_dict()
        # And for the audit entry, which is written once the row actually is
        # gone. The instance is only detached by then, so attributes already
        # loaded still read back, but nothing guarantees that: a lazy column
        # or a session configured to expire on commit would raise, and the
        # entry would be lost on a deletion that succeeded. The fallback
        # chain is the one `log_ca` applied, kept here because a record whose
        # name is empty otherwise reaches the ledger with no name at all.
        _ca_id = ca.id
        _ca_descr = ca.descr
        _ca_name = _ca_descr or getattr(ca, 'subject', None) or f'CA #{_ca_id}'

        # A record that signs for its key may have published any revocation of that key (#450)
        from services.cert.local_revocation import publish_before_deletion
        publish_before_deletion(ca)

        # Rows that must not outlive the authority. This used to sit in the
        # unit route, which is why the bulk route -- the other caller of this
        # service -- orphaned every one of them.
        purged = purge_ca_dependents(ca)
        if purged:
            logger.info(f"{purged} for CA {_ca_name}")

        # The files go after the commit: a refused delete (a foreign key the
        # blockers did not know) must leave the authority whole. The row is
        # expired by then, so the file helpers read a detached copy.
        _ca_files = SimpleNamespace(
            **{column.key: getattr(ca, column.key) for column in CA.__table__.columns}
        )

        # Delete from database
        db.session.delete(ca)
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed deleting CA {_ca_id}: {_commit_err}", exc_info=True)
            # Recording the failure is safe here because the rollback has
            # emptied the session, so this commit carries nothing but the entry.
            AuditService.log_action(
                action='ca_deleted',
                resource_type='ca',
                resource_id=_ca_id,
                resource_name=_ca_name,
                details='Failed to delete CA; nothing on disk was touched',
                success=False,
            )
            raise

        # Nothing after the commit may contradict it: a file that will not go
        # is logged, not reported as a failed deletion
        try:
            delete_ca_files(_ca_files)
        except Exception as e:
            logger.warning(f"CA {_ca_name} deleted, its files could not be removed: {e}")

        # Audit after the delete has committed, not before it. `log_action`
        # commits the session it is given, so an entry written first said the
        # authority had been deleted and was durable while the deletion still
        # was not. Anything failing after it -- and the files on disk are
        # already unlinked by then -- left the trail asserting a deletion the
        # database contradicts, in the one place left that could say what
        # happened. Same fields `log_ca` would have built, read from the
        # object while it still answered.
        AuditService.log_action(
            action='ca_deleted',
            resource_type='ca',
            resource_id=_ca_id,
            resource_name=_ca_name,
            details=f'Deleted CA: {_ca_descr}',
        )

        from services.webhook_service import emit_ca_deleted
        emit_ca_deleted(_ca_snapshot, actor=username)

        return True
