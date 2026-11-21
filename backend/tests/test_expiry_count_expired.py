"""The count of expiries left aside after an outage is the count of announcements dropped."""
import uuid
from datetime import datetime, timedelta

import pytest

from models import db
from models.ca_cross_certificate import CACrossCertificate
from services import expiry_alert_service


def test_an_orphan_cross_certificate_is_neither_announced_nor_counted(app):
    # A year no other test uses: nothing else expires in this window
    expired = datetime(2048, 3, 1, 12, 0)
    with app.app_context():
        if db.engine.dialect.name != 'sqlite':
            pytest.skip('an orphan row needs SQLite, which does not enforce the foreign key here')
        missing_ca = (db.session.query(db.func.max(CACrossCertificate.ca_id)).scalar() or 0) + 10 ** 6
        row = CACrossCertificate(ca_id=missing_ca, crt='x', fingerprint_sha256=uuid.uuid4().hex * 2,
                                 valid_to=expired)
        db.session.add(row)
        db.session.commit()
        try:
            after, until = expired - timedelta(days=1), expired + timedelta(days=1)
            from services.ca.cross_certs import expiring_alerts
            _, gone = expiring_alerts(now=until, expired_after=after)
            assert gone == []
            assert expiry_alert_service.count_expired_between(after, until) == len(gone)
        finally:
            db.session.delete(row)
            db.session.commit()
