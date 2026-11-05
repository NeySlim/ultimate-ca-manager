"""One renewal or finalization at a time per ACME client order.

The lease is a timestamp in the order's row, taken by a conditional UPDATE: a manual
renewal, the scheduler and a finalization in another worker or process exclude each
other. A holder that dies leaves it to expire after LEASE_DURATION.
"""
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import or_

from models import db
from models.acme_models import AcmeClientOrder
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

LEASE_DURATION = timedelta(minutes=10)
LEASE_LOST = 'Another finalization of this order took over'
BUSY = 'A renewal or finalization of this order is already running: try again later'


class RenewalInProgress(Exception):
    """Another renewal or finalization holds the order."""


class OrderLease:
    """A lease held on one order; the timestamp written is the holder's token."""

    def __init__(self, order_id: int, token):
        self.order_id = order_id
        self.token = token

    @classmethod
    def take(cls, order_id: int) -> Optional['OrderLease']:
        """The lease, or None while another holder's is live. Commits the session."""
        now = utc_now()
        taken = AcmeClientOrder.query.filter(
            AcmeClientOrder.id == order_id,
            or_(AcmeClientOrder.renewal_claimed_at.is_(None),
                AcmeClientOrder.renewal_claimed_at < now - LEASE_DURATION),
        ).update({'renewal_claimed_at': now}, synchronize_session=False)
        db.session.commit()
        return cls(order_id, now) if taken == 1 else None

    def _held(self):
        return AcmeClientOrder.query.filter(
            AcmeClientOrder.id == self.order_id, AcmeClientOrder.renewal_claimed_at == self.token)

    def refresh(self) -> bool:
        """Restart the lease and commit the session while it is this holder's; once it is
        another's, roll the session back and answer False."""
        now = utc_now()
        if self._held().update({'renewal_claimed_at': now}, synchronize_session=False) != 1:
            db.session.rollback()
            return False
        db.session.commit()
        self.token = now
        return True

    def release(self) -> None:
        """Give the lease back unless another holder took it over; never raises."""
        for _attempt in range(2):
            try:
                self._held().update({'renewal_claimed_at': None}, synchronize_session=False)
                db.session.commit()
                return
            except Exception as exc:  # a failed transaction of the holder's own
                db.session.rollback()
                logger.warning("Lease of ACME order %s not released: %s", self.order_id, exc)
