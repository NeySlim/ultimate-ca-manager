"""TOTP verification with one-time use (RFC 6238 §5.2)."""
import hmac
import time

import pyotp
from sqlalchemy import or_, update
from sqlalchemy.orm.attributes import set_committed_value

from models import User, db

# One time step of clock drift either way, as RFC 6238 §5.2 recommends at most.
VALID_WINDOW = 1


def matched_step(secret, code, now=None):
    """Time step whose code equals ``code`` within the window, or None."""
    if not secret or not code:
        return None
    totp = pyotp.TOTP(secret)
    current = int((time.time() if now is None else now) // totp.interval)
    code = str(code).strip()
    for step in range(current - VALID_WINDOW, current + VALID_WINDOW + 1):
        if hmac.compare_digest(totp.generate_otp(step), code):
            return step
    return None


def consume_totp(user, code) -> bool:
    """Accept ``code`` once: its step must be later than the last one accepted.

    The step is claimed with a conditional UPDATE in the caller's transaction,
    so two requests racing with the same code cannot both succeed; the caller
    commits.
    """
    if not user.totp_secret:
        return False
    step = matched_step(user.totp_secret, code)
    if step is None:
        return False
    claimed = db.session.execute(
        update(User)
        .where(User.id == user.id,
               or_(User.totp_last_step.is_(None), User.totp_last_step < step))
        .values(totp_last_step=step)
        .execution_options(synchronize_session=False)
    ).rowcount
    if claimed != 1:
        return False
    set_committed_value(user, 'totp_last_step', step)
    return True
