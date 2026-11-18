"""The restore job's end steps, stubbed where a test stubbed invalidate_after_restore before."""


def sessions_kept(monkeypatch):
    """The sessions step claims its mark and revokes nothing: the test's own session stays."""
    from models import db
    from services.backup.restore import invalidate

    def keep(claim):
        counts = {'sessions_revoked': 0, 'sso_sessions_revoked': 0, 'flask_sessions_revoked': 0}
        if not claim(counts):
            db.session.rollback()
            return None
        db.session.commit()
        return counts
    monkeypatch.setattr(invalidate, 'revoke_sessions_with', keep)
    monkeypatch.setattr(invalidate, 'remove_session_files', lambda older_than=None: 0)
