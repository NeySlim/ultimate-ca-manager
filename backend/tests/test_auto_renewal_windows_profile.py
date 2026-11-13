"""The scheduler leaves a certificate of a Windows enrollment profile to Windows."""
import datetime
import uuid

from models import Certificate, db
from services.auto_renewal_service import AutoRenewalService
from utils.datetime_utils import utc_now


def test_a_windows_profile_certificate_is_never_due_for_auto_renewal(app, monkeypatch):
    monkeypatch.setattr(AutoRenewalService, 'get_renewal_config', staticmethod(lambda: {
        'enabled': True, 'days_before_expiry': 30, 'renewal_sources': ['manual']}))
    tag, now = uuid.uuid4().hex[:8], utc_now()
    with app.app_context():
        rows = [Certificate(refid=f'q-{tag}-{kind}', descr=f'q {kind}', crt='eA==', prv='eA==', source='manual',
                            valid_from=now - datetime.timedelta(days=90), valid_to=now + datetime.timedelta(days=5),
                            windows_profile_id=profile_id)
                for kind, profile_id in (('plain', None), ('windows', 987654))]
        db.session.add_all(rows)
        db.session.commit()
        ids = {row.descr: row.id for row in rows}
        try:
            due = {c.id for c in AutoRenewalService.get_certificates_for_renewal()}
            assert ids['q plain'] in due
            assert ids['q windows'] not in due
        finally:
            Certificate.query.filter(Certificate.id.in_(ids.values())).delete(synchronize_session=False)
            db.session.commit()
