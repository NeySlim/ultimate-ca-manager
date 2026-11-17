"""Purge of OIDC and SAML sign-in tests past their expiry: a report holds the name, e-mail
and groups of the identity tried, kept 10 minutes after the return and no longer."""
import logging
from datetime import timedelta

from sqlalchemy import delete, or_, update

from models import db
from models.sso import SSOSignInTest
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

# An expired row stays this long, emptied, so a late return is still answered as a test's.
TOMBSTONE_TTL = timedelta(hours=24)


def purge_expired_sign_in_tests():
    """In the caller's transaction: erase the report and secrets of what expired, keep the row
    as a tombstone, delete it a day later; returns how many rows were erased or deleted."""
    now = utc_now()
    removed = db.session.execute(
        delete(SSOSignInTest).where(SSOSignInTest.expires_at < now - TOMBSTONE_TTL)).rowcount
    erased = db.session.execute(update(SSOSignInTest).where(
        SSOSignInTest.expires_at < now,
        or_(SSOSignInTest.report.is_not(None), SSOSignInTest.secret.is_not(None),
            SSOSignInTest.browser_hash != '')).values(
        report=None, secret=None, browser_hash='')).rowcount
    return removed + erased


def scheduled_purge():
    """Scheduler entry point: where nobody starts, returns or reads a test, reports still go."""
    try:
        removed = purge_expired_sign_in_tests()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    if removed:
        logger.info("Sign-in test purge: erased or removed %d expired tests", removed)
    return {'status': 'ok', 'reason': None}
