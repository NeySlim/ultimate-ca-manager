"""Two executors of the same scheduled work (two leaders in turn, a run-now beside the
scheduler): the conditional claim lets exactly one act.

Discovery claims a due profile by moving next_scan_at from the value it read; the OCSP
responder renewal rebinds the responder only if the binding still names the old certificate.
"""
import base64
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from models import Certificate, ScanProfile, SystemConfig, db
from services.discovery import DiscoveryService
from services.discovery_scheduler_task import DiscoverySchedulerTask
from tests.test_crl_number_monotonic import _authority, _ca_row
from tests.test_discovery_scanner import _make_profile
from utils.datetime_utils import utc_now
from utils.key_codec import store_pem_bytes

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
_on_pg = [pytest.mark.postgres, pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]


def _pg(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    import contextlib

    @contextlib.contextmanager
    def bound():
        with _a_schema_of_our_own(f'claims_{uuid.uuid4().hex[:6]}') as url, \
                _bound_to(app, url, is_postgresql=True):
            yield
    return bound()


def _twice_at_once(app, run, meet_in, attribute):
    """Run *run* in two threads that both pass the read before either claims."""
    original = getattr(meet_in, attribute)
    both = threading.Barrier(2, timeout=10)

    def meet_then(*args, **kwargs):
        try:
            both.wait()
        except threading.BrokenBarrierError:
            pass
        return original(*args, **kwargs)

    results, errors = [], []

    def worker():
        try:
            with app.app_context():
                results.append(run())
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    setattr(meet_in, attribute, staticmethod(meet_then) if isinstance(meet_in, type) else meet_then)
    try:
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
    finally:
        setattr(meet_in, attribute, staticmethod(original) if isinstance(meet_in, type) else original)
    assert errors == []
    return results


# ------------------------------------------------------------------ discovery

def test_a_stale_profile_is_not_claimed_twice(app):
    with app.app_context():
        now = datetime.now(timezone.utc)
        profile = _make_profile(f'claim-{uuid.uuid4().hex[:6]}', now - timedelta(minutes=5))
        stale = ScanProfile(id=profile.id, name=profile.name, next_scan_at=profile.next_scan_at,
                            schedule_interval_minutes=60)
        assert DiscoverySchedulerTask._advance_next_scan(profile, now) is True
        assert DiscoverySchedulerTask._advance_next_scan(stale, now) is False


def _discovery_race(app, monkeypatch):
    started = []
    monkeypatch.setattr(DiscoveryService, 'start_scan', lambda self, **kw: started.append(kw) or 1)
    with app.app_context():
        _make_profile(f'claim-{uuid.uuid4().hex[:6]}', datetime.now(timezone.utc) - timedelta(minutes=5))
        db.session.remove()
    _twice_at_once(app, DiscoverySchedulerTask.execute, DiscoverySchedulerTask, '_advance_next_scan')
    return started


@pytest.mark.parametrize('_', [0], ids=['sqlite'])
def test_two_discovery_executors_start_one_scan_on_sqlite(app, monkeypatch, tmp_path, _):
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'claims.db'}"):
        assert len(_discovery_race(app, monkeypatch)) == 1


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_two_discovery_executors_start_one_scan_on_postgresql(app, monkeypatch):
    with _pg(app):
        assert len(_discovery_race(app, monkeypatch)) == 1


# ------------------------------------------------------------- OCSP responder

def _responder(ca, ca_key, ca_cert):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'claims-ocsp')]))
            .issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=85)).not_valid_after(now + timedelta(days=5))
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.OCSP_SIGNING]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    row = Certificate(
        refid=uuid.uuid4().hex[:8], descr='claims-ocsp', caref=ca.refid, cert_type='custom',
        crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
        prv=store_pem_bytes(key.private_bytes(serialization.Encoding.PEM,
                                              serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption())),
        subject=cert.subject.rfc4514_string(), subject_cn='claims-ocsp',
        issuer=cert.issuer.rfc4514_string(), serial_number=str(cert.serial_number),
        valid_from=utc_now() - timedelta(days=85), valid_to=utc_now() + timedelta(days=5))
    db.session.add(row)
    db.session.commit()
    db.session.add(SystemConfig(key=f'ocsp_responder_cert_{ca.id}', value=str(row.id)))
    db.session.commit()
    return row.id


def test_a_stale_binding_is_not_rebound(app):
    from services.ocsp_responder_renewal import _rebind
    with app.app_context():
        key = f'ocsp_responder_cert_claims_{uuid.uuid4().hex[:6]}'
        db.session.add(SystemConfig(key=key, value='7'))
        db.session.commit()
        assert _rebind(key, 7, 8) is True
        assert _rebind(key, 7, 9) is False
        db.session.commit()
        assert SystemConfig.query.filter_by(key=key).one().value == '8'


def _ocsp_race(app):
    import services.ocsp_responder_renewal as renewal
    with app.app_context():
        ca_key, ca_cert = _authority()
        ca = _ca_row(ca_key, ca_cert)
        old_id, ca_id = _responder(ca, ca_key, ca_cert), ca.id
        db.session.remove()
    stats = _twice_at_once(app, renewal.run_ocsp_responder_renewal, renewal, '_renew_responder_cert')
    with app.app_context():
        bound = int(SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca_id}').one().value)
        renewed = Certificate.query.filter_by(created_by='system:ocsp-renewal').all()
        db.session.remove()
    return old_id, bound, [r.id for r in renewed], stats


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_two_ocsp_renewal_runners_renew_once_on_postgresql(app):
    with _pg(app):
        old_id, bound, renewed, stats = _ocsp_race(app)
    assert sorted(s['renewed'] for s in stats) == [0, 1], stats
    assert renewed == [bound] and bound != old_id
