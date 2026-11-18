"""Two revocations of one SSH certificate: the second is refused as for a certificate already
revoked, and never rewrites the date and reason of the first, even when the first committed
after the second read the row (SQLite takes no row lock)."""
import datetime
import os
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

import services.ssh_cert.management as management
from models import SSHCertificate, db
from services.ssh_cert import SSHCertificateService
from tests.test_ssh_serial_concurrency import _ca, _pubkey

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
TABLE = SSHCertificate.__table__
FIRST = datetime.datetime(2026, 1, 2, 3, 4, 5)


def _another_request_revokes(cert_id):
    with db.engine.begin() as conn:
        conn.execute(TABLE.update().where(TABLE.c.id == cert_id).values(
            revoked=True, revoked_at=FIRST, revoke_reason='superseded'))


def _stored(cert_id):
    with db.engine.connect() as conn:
        revoked, at, reason = conn.execute(select(TABLE.c.revoked, TABLE.c.revoked_at, TABLE.c.revoke_reason)
                                           .where(TABLE.c.id == cert_id)).one()
    return bool(revoked), at.replace(tzinfo=None) if at else None, reason


def _check(app):
    """Revoke a certificate while another request commits its own revocation of it between
    this one's read and its write."""
    with app.app_context():
        ca_id = _ca('Revoke race').id
        cert_id = SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', ['alice']).id
        db.session.remove()
        real = management.utc_now

        def overtaken():
            _another_request_revokes(cert_id)
            return real()

        with patch.object(management, 'utc_now', side_effect=overtaken), \
                pytest.raises(ValueError, match='^Certificate is already revoked$'):
            SSHCertificateService.revoke_certificate(cert_id, 'keyCompromise', 'admin')
        db.session.remove()
        assert _stored(cert_id) == (True, FIRST, 'superseded')
        db.session.remove()


def test_a_revocation_overtaken_keeps_the_first_on_sqlite(app, tmp_path):
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'ssh-revoke.db'}"):
        _check(app)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_a_revocation_overtaken_keeps_the_first_on_postgresql(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'ssh_revoke_race_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        _check(app)
