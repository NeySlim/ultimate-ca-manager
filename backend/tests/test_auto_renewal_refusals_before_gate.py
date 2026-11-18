"""The scheduler refuses a certificate no renewal could honour before the approval gate, as the
routes do: the failure carries the routes' reason, is recorded once, opens no approval request,
and the next certificate of the pass is renewed."""
import base64
import json

import pytest
from sqlalchemy import update

import fips_mode
from models import Certificate, db
from models.policy import ApprovalRequest, CertificatePolicy
from tests.test_approval_on_sign_and_renew import _cert_row, _drop_policy, _drop_rows, _json

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _renewal_policy(app, ca_id, name):
    """A policy that holds renewals, the scheduler's included."""
    with app.app_context():
        pol = CertificatePolicy(name=f'{name}-{ca_id}', ca_id=ca_id, requires_approval=True,
                                min_approvers=1, is_active=True, priority=100)
        pol.set_operations(['renewal'])
        pol.set_rules({})
        db.session.add(pol)
        db.session.commit()
        return pol.id


def _revoke_now(cert_id):
    from utils.datetime_utils import utc_now
    db.session.execute(update(Certificate).where(Certificate.id == cert_id).values(
        revoked=True, revoked_at=utc_now(), revoke_reason='keyCompromise'))
    db.session.commit()


def _spoil(kind, cert_id, monkeypatch):
    """Make the row one no renewal could honour; 'revoked' is applied after the listing."""
    row = db.session.get(Certificate, cert_id)
    if kind == 'unreadable':
        row.crt = base64.b64encode(b'not a certificate').decode()
    elif kind == 'msca':
        row.source = 'msca'
    elif kind == 'eddsa_fips':
        row.key_algo = 'Ed25519'
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        monkeypatch.setattr(fips_mode, 'module_approves', lambda alg: False)
    db.session.commit()


def _requests_naming(cert_id):
    out = []
    for ap in ApprovalRequest.query.filter_by(request_type='renewal').all():
        try:
            data = json.loads(ap.request_data or '{}')
        except ValueError:
            continue
        if isinstance(data, dict) and data.get('certificate_id') == cert_id:
            out.append(ap.id)
    return out


@pytest.mark.parametrize('kind', ['revoked', 'eddsa_fips', 'msca', 'unreadable'])
def test_a_refused_certificate_fails_with_the_routes_reason_before_the_gate(
        app, auth_client, create_ca, monkeypatch, kind):
    from services.auto_renewal_service import AutoRenewalService as svc
    gated = create_ca(cn=f'gate-{kind} CA')
    free = create_ca(cn=f'free-{kind} CA')
    pid = _renewal_policy(app, gated['id'], f'gate-{kind}')
    bad_id = _cert_row(app, gated['id'], f'bad-{kind}.example.test')
    held_id = _cert_row(app, gated['id'], f'held-{kind}.example.test')
    next_id = _cert_row(app, free['id'], f'next-{kind}.example.test')
    reasons = []
    monkeypatch.setattr(svc, '_log_failure', staticmethod(
        lambda cert_id, cn, reason: reasons.append((cert_id, reason))))
    monkeypatch.setattr(svc, '_send_failure_notification', staticmethod(lambda stats: None))
    monkeypatch.setattr(svc, '_publish_crls', staticmethod(lambda carefs: None))
    try:
        with app.app_context():
            previous = dict(svc.get_renewal_config())
            _spoil(kind, bad_id, monkeypatch)

            def listing():
                rows = [db.session.get(Certificate, i) for i in (bad_id, held_id, next_id)]
                if kind == 'revoked':  # revoked between the listing and its turn
                    _revoke_now(bad_id)
                return rows

            monkeypatch.setattr(svc, 'get_certificates_for_renewal', staticmethod(listing))
            svc.set_renewal_config({**previous, 'enabled': True})
            try:
                stats = svc.run_auto_renewal()
            finally:
                svc.set_renewal_config(previous)
            assert _requests_naming(bad_id) == []
            assert len(_requests_naming(held_id)) == 1  # the gate holds this CA's renewals
            assert (db.session.get(Certificate, next_id).renewed_times or 0) == 1
            db.session.remove()
        assert (stats['renewed'], stats['failed'], stats['queued']) == (1, 1, 1), stats
        r = _json(auth_client, 'post', '/api/v2/certificates/bulk/renew', {'ids': [bad_id]})
        [failed] = r.get_json()['data']['failed']
        assert reasons == [(bad_id, failed['error'])], (reasons, failed)
    finally:
        _drop_policy(app, pid)
        _drop_rows(app, bad_id, held_id, next_id)


@pytest.mark.parametrize('kind', ['overtaken', 'gone'])
def test_a_certificate_overtaken_or_gone_before_the_gate_is_skipped(
        app, create_ca, monkeypatch, kind):
    """As when the renewal itself is overtaken: the next pass reads the row anew, nothing is
    recorded as a failure and no approval request is opened."""
    import services.auto_renewal_service as scheduler
    from services.cert.renewal import RenewalError
    svc = scheduler.AutoRenewalService
    gated = create_ca(cn=f'gate-{kind} CA')
    pid = _renewal_policy(app, gated['id'], f'gate-{kind}')
    bad_id = _cert_row(app, gated['id'], f'bad-{kind}.example.test')
    reasons = []
    monkeypatch.setattr(svc, '_log_failure', staticmethod(
        lambda cert_id, cn, reason: reasons.append((cert_id, reason))))
    monkeypatch.setattr(svc, '_send_failure_notification', staticmethod(lambda stats: None))
    monkeypatch.setattr(svc, '_publish_crls', staticmethod(lambda carefs: None))

    def refuse(cert, trigger):
        if kind == 'overtaken':
            raise RenewalError('Certificate was renewed by another request', 409, overtaken=True)
        db.session.execute(Certificate.__table__.delete().where(Certificate.id == bad_id))
        db.session.commit()
        raise RenewalError('Certificate no longer exists', 404)

    monkeypatch.setattr(scheduler, 'check_renewable', refuse)
    try:
        with app.app_context():
            previous = dict(svc.get_renewal_config())
            monkeypatch.setattr(svc, 'get_certificates_for_renewal', staticmethod(
                lambda: [db.session.get(Certificate, bad_id)]))
            svc.set_renewal_config({**previous, 'enabled': True})
            try:
                stats = svc.run_auto_renewal()
            finally:
                svc.set_renewal_config(previous)
            assert _requests_naming(bad_id) == []
            db.session.remove()
        assert (stats['skipped'], stats['failed'], stats['queued']) == (1, 0, 0), stats
        assert reasons == []
    finally:
        _drop_policy(app, pid)
        _drop_rows(app, bad_id)
