"""A signed-in session posed by a test, holding what `begin_session` and a login put there."""
from utils.datetime_utils import utc_now


def pose_signed_in(sess, user):
    """Write into ``sess`` (a `session_transaction()`) the keys a login gives ``user``.

    Needs an app context. The epoch is the current one: a session posed without it
    reads as begun before every restore and is refused.
    """
    from auth.session_epoch import SESSION_KEY, current_epoch
    from auth.session_start import ACCOUNT_KEY, account_proof
    now = utc_now().isoformat()
    sess.update(user_id=user.id, username=user.username,
                session_version=user.session_version or 0,
                login_time=now, last_activity=now,
                **{ACCOUNT_KEY: account_proof(user), SESSION_KEY: current_epoch()})
