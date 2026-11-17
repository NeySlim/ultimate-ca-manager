"""Purge of OIDC and SAML sign-in tests past their expiry: a report holds the name, e-mail
and groups of the identity tried, kept 10 minutes after the return and no longer."""
import logging

from sqlalchemy import delete

from models import db
from models.sso import SSOSignInTest
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


def purge_expired_sign_in_tests():
    """Delete the expired rows in the caller's transaction; returns how many went."""
    return db.session.execute(
        delete(SSOSignInTest).where(SSOSignInTest.expires_at < utc_now())).rowcount


def scheduled_purge():
    """Scheduler entry point: where nobody starts, returns or reads a test, reports still go."""
    try:
        removed = purge_expired_sign_in_tests()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    if removed:
        logger.info("Sign-in test purge: removed %d expired tests", removed)
    return {'status': 'ok', 'reason': None}
