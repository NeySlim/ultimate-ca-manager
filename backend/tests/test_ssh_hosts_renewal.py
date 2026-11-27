"""SSH host renewal (issue #451): the host asks /ssh/renew/<refid>/challenge, signs the challenge
with the key its current certificate certifies, and gets a certificate with the same names.
No stored secret authenticates it: a revoked host or certificate, a disabled renewal, another
key, a replayed or expired challenge are refused, and audited."""
import json
import shutil
import subprocess
from datetime import timedelta

import pytest

from models import AuditLog, db
from models.ssh import SSHCertificate, SSHHost
from services import ssh_host_service as hosts
from utils.datetime_utils import utc_now
from tests.test_ssh import _create_ssh_ca, post_json
from tests.ssh_cleanup import ssh_rows_stay_in_their_module  # noqa: F401

pytestmark = pytest.mark.skipif(not shutil.which('ssh-keygen'), reason='ssh-keygen not available')


@pytest.fixture
def enrolled(app, auth_client, client, tmp_path):
    """(ca, host refid, host private key path) of a host enrolled for web01 and web01.example.com."""
    ca = _create_ssh_ca(auth_client, ca_type='host', descr=f'Renewal CA {tmp_path.name}')
    key = tmp_path / 'ssh_host_ed25519_key'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    token = post_json(auth_client, '/api/v2/ssh/enrollment-tokens', {
        'ca_id': ca['id'], 'principals': ['web01.example.com', 'web01'], 'validity_seconds': 86400,
    }).get_json()['data']['token']
    r = client.post(f"/ssh/enroll/{ca['refid']}", data=json.dumps({
        'token': token, 'public_key': (tmp_path / 'ssh_host_ed25519_key.pub').read_text(),
        'signature': _sign(tmp_path, key, token, hosts.ENROLL_NAMESPACE)}),
        content_type='application/json')
    assert r.status_code == 201, r.data
    return ca, r.get_json()['host_refid'], key


def _age(app, refid, issued_days_ago=10):
    """The current certificate issued long ago: its last share of life has begun."""
    with app.app_context():
        cert = SSHHost.query.filter_by(refid=refid).one().certificate
        cert.created_at = utc_now() - timedelta(days=issued_days_ago)
        db.session.commit()


def _sign(tmp_path, key, challenge, namespace=hosts.NAMESPACE):
    (tmp_path / 'challenge').write_text(challenge)
    subprocess.run(['ssh-keygen', '-q', '-Y', 'sign', '-n', namespace, '-f', str(key), str(tmp_path / 'challenge')],
                   check=True)
    signature = (tmp_path / 'challenge.sig').read_text()
    (tmp_path / 'challenge.sig').unlink()
    return signature


def _challenge(client, refid):
    return client.post(f'/ssh/renew/{refid}/challenge')


def _renew(client, refid, challenge, signature):
    return client.post(f'/ssh/renew/{refid}', data=json.dumps({'challenge': challenge, 'signature': signature}),
                       content_type='application/json')


def _since(app):
    with app.app_context():
        return db.session.query(db.func.max(AuditLog.id)).scalar() or 0


def _audits(app, since, action):
    with app.app_context():
        rows = AuditLog.query.filter(AuditLog.id > since, AuditLog.action == action).order_by(AuditLog.id)
        return [(a.success, a.details) for a in rows]


class TestTheChallenge:
    def test_a_young_certificate_is_not_due(self, app, client, enrolled):
        _, refid, _ = enrolled
        r = _challenge(client, refid)
        assert r.status_code == 200 and r.get_json()['due'] == 0 and 'challenge' not in r.get_json()
        with app.app_context():
            host = SSHHost.query.filter_by(refid=refid).one()
            cert = host.certificate
            # 30 % of the lifetime it was issued with, before its end
            window = cert.valid_to - (cert.valid_to - cert.created_at) * 0.3
            assert r.get_json()['renew_after'].startswith(window.strftime('%Y-%m-%dT%H:%M'))
            assert host.challenge is None and host.last_seen_at is not None

    def test_in_its_last_share_it_hands_out_one_challenge(self, app, client, enrolled):
        _, refid, _ = enrolled
        _age(app, refid)
        first = _challenge(client, refid).get_json()
        assert first['due'] == 1 and first['namespace'] == 'ucm-ssh-host-renewal' and len(first['challenge']) >= 40
        # Asked again, the pending one: a stranger cannot void it
        assert _challenge(client, refid).get_json()['challenge'] == first['challenge']

    def test_text_plain_answers_in_lines(self, app, client, enrolled):
        _, refid, _ = enrolled
        _age(app, refid)
        r = client.post(f'/ssh/renew/{refid}/challenge', headers={'Accept': 'text/plain'})
        assert r.mimetype == 'text/plain' and 'due=1\n' in r.data.decode()

    def test_an_unknown_host_is_404(self, client):
        r = _challenge(client, '00000000-0000-0000-0000-000000000000')
        assert r.status_code == 404 and r.get_json()['state'] == 'unknown'

    def test_a_disabled_renewal_is_refused_without_an_audit_at_every_sync(self, app, auth_client, client, enrolled):
        _, refid, _ = enrolled
        with app.app_context():
            host_id = SSHHost.query.filter_by(refid=refid).one().id
        post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/auto-renew', {'enabled': False})
        since = _since(app)
        r = _challenge(client, refid)
        assert r.status_code == 403 and r.get_json()['state'] == 'disabled'
        assert _audits(app, since, 'ssh_host_renewal_refused') == []


class TestTheRenewal:
    def test_the_signed_challenge_buys_a_certificate_with_the_same_names(self, app, client, enrolled, tmp_path):
        _, refid, key = enrolled
        _age(app, refid)
        with app.app_context():
            before = SSHHost.query.filter_by(refid=refid).one().certificate_id
        challenge = _challenge(client, refid).get_json()['challenge']
        since = _since(app)
        r = _renew(client, refid, challenge, _sign(tmp_path, key, challenge))
        assert r.status_code == 200, r.data
        with app.app_context():
            host = SSHHost.query.filter_by(refid=refid).one()
            assert host.certificate_id != before and host.certificate.certificate == r.get_json()['certificate']
            assert host.certificate.get_principals() == ['web01.example.com', 'web01']
            assert host.certificate.source == 'renewal' and host.last_renewed_at is not None
            assert host.challenge is None
            assert not db.session.get(SSHCertificate, before).revoked
            # The new certificate is young: nothing is due
        assert _challenge(client, refid).get_json()['due'] == 0
        [(ok, details)] = _audits(app, since, 'ssh_host_renewed')
        assert ok and 'web01.example.com, web01' in details

    def test_a_challenge_is_spent_once(self, app, client, enrolled, tmp_path):
        _, refid, key = enrolled
        _age(app, refid)
        challenge = _challenge(client, refid).get_json()['challenge']
        signature = _sign(tmp_path, key, challenge)
        assert _renew(client, refid, challenge, signature).status_code == 200
        _age(app, refid)
        assert _renew(client, refid, challenge, signature).status_code == 403

    def test_another_key_or_purpose_or_message_is_refused_and_audited(self, app, client, enrolled, tmp_path):
        _, refid, _ = enrolled
        _age(app, refid)
        stranger = tmp_path / 'stranger'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(stranger)], check=True)
        challenge = _challenge(client, refid).get_json()['challenge']
        since = _since(app)
        assert _renew(client, refid, challenge, _sign(tmp_path, stranger, challenge)).status_code == 403
        assert _renew(client, refid, challenge, _sign(tmp_path, enrolled[2], challenge, 'file')).status_code == 403
        assert _renew(client, refid, challenge, _sign(tmp_path, enrolled[2], challenge + 'x')).status_code == 403
        assert _renew(client, refid, 'not-the-challenge', _sign(tmp_path, enrolled[2], challenge)).status_code == 403
        details = [d for ok, d in _audits(app, since, 'ssh_host_renewal_refused') if not ok]
        assert [d.split(': ', 2)[-1] for d in details] == [
            'signed with another key', 'signed for another purpose', 'the signature does not verify',
            'no such pending challenge']
        # None of them spent the challenge
        assert _renew(client, refid, challenge, _sign(tmp_path, enrolled[2], challenge)).status_code == 200

    def test_an_expired_challenge_is_refused(self, app, client, enrolled, tmp_path):
        _, refid, key = enrolled
        _age(app, refid)
        challenge = _challenge(client, refid).get_json()['challenge']
        with app.app_context():
            SSHHost.query.filter_by(refid=refid).one().challenge_expires_at = utc_now() - timedelta(seconds=1)
            db.session.commit()
        assert _renew(client, refid, challenge, _sign(tmp_path, key, challenge)).status_code == 403

    def test_a_revoked_host_or_certificate_cannot_renew(self, app, auth_client, client, enrolled, tmp_path):
        _, refid, key = enrolled
        _age(app, refid)
        challenge = _challenge(client, refid).get_json()['challenge']
        with app.app_context():
            host = SSHHost.query.filter_by(refid=refid).one()
            host_id, cert_id = host.id, host.certificate_id
        # The certificate revoked on the certificates page: the proof rests on an unrevoked one
        assert post_json(auth_client, f'/api/v2/ssh/certificates/{cert_id}/revoke', {}).status_code == 200
        r = _renew(client, refid, challenge, _sign(tmp_path, key, challenge))
        assert r.status_code == 403 and r.get_json()['state'] == 'revoked'
        assert post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/revoke', {}).status_code == 200
        r = _challenge(client, refid)
        assert r.status_code == 403 and r.get_json()['state'] == 'revoked'

    def test_revoking_the_host_revokes_the_certificates_a_renewal_replaced(self, app, auth_client, client,
                                                                           enrolled, tmp_path):
        ca, refid, key = enrolled
        _age(app, refid)
        with app.app_context():
            host = SSHHost.query.filter_by(refid=refid).one()
            host_id, old = host.id, host.certificate.certificate
        challenge = _challenge(client, refid).get_json()['challenge']
        assert _renew(client, refid, challenge, _sign(tmp_path, key, challenge)).status_code == 200
        assert post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/revoke', {}).status_code == 200
        (tmp_path / 'krl').write_bytes(client.get(f"/ssh/krl/{ca['refid']}").data)
        (tmp_path / 'old-cert.pub').write_text(old)
        # 1: revoked, 0: still accepted by a client checking the host CA's KRL
        out = subprocess.run(['ssh-keygen', '-Q', '-f', str(tmp_path / 'krl'), str(tmp_path / 'old-cert.pub')],
                             capture_output=True, text=True, timeout=30)
        assert out.returncode == 1, out.stdout + out.stderr

    def test_a_renewal_during_the_revocation_of_its_host_is_refused(self, app, auth_client, client, enrolled,
                                                                    tmp_path, monkeypatch):
        _, refid, key = enrolled
        _age(app, refid)
        challenge = _challenge(client, refid).get_json()['challenge']
        signature = _sign(tmp_path, key, challenge)
        with app.app_context():
            host_id = SSHHost.query.filter_by(refid=refid).one().id
        real, outcome = hosts._live_certificates_of_key, []

        def renewal_meanwhile(host):
            # The host's renewal lands while the revocation looks for its certificates
            if not outcome:
                try:
                    hosts.renew(refid, challenge, signature)
                    outcome.append('renewed')
                except hosts.RenewalRefused as e:
                    outcome.append(e.state)
            return real(host)
        monkeypatch.setattr(hosts, '_live_certificates_of_key', renewal_meanwhile)
        assert post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/revoke', {}).status_code == 200
        assert outcome == ['revoked']

    def test_a_certificate_signed_while_its_host_was_revoked_is_revoked(self, app, auth_client, client,
                                                                        enrolled, tmp_path, monkeypatch):
        from services.ssh_cert import SSHCertificateService
        _, refid, key = enrolled
        _age(app, refid)
        challenge = _challenge(client, refid).get_json()['challenge']
        with app.app_context():
            host = SSHHost.query.filter_by(refid=refid).one()
            host_id, before = host.id, host.certificate_id
        real = SSHCertificateService.sign_certificate

        def revoked_first(*args, **kwargs):
            # The revocation took its snapshot of the key's certificates before this one existed
            hosts.revoke_host(host_id)
            return real(*args, **kwargs)
        monkeypatch.setattr(SSHCertificateService, 'sign_certificate', revoked_first)
        r = _renew(client, refid, challenge, _sign(tmp_path, key, challenge))
        assert r.status_code == 403 and r.get_json()['state'] == 'revoked'
        with app.app_context():
            renewed = SSHCertificate.query.filter(SSHCertificate.ssh_ca_id == enrolled[0]['id'],
                                                  SSHCertificate.source == 'renewal').all()
            assert len(renewed) == 1 and renewed[0].revoked
            assert SSHHost.query.filter_by(refid=refid).one().certificate_id == before

    def test_a_revocation_cut_short_is_finished_by_the_next_one(self, app, auth_client, client, enrolled,
                                                                tmp_path, monkeypatch):
        from sqlalchemy.exc import OperationalError
        from services.ssh_cert import SSHCertificateService
        _, refid, key = enrolled
        _age(app, refid)
        challenge = _challenge(client, refid).get_json()['challenge']
        assert _renew(client, refid, challenge, _sign(tmp_path, key, challenge)).status_code == 200
        with app.app_context():
            host = SSHHost.query.filter_by(refid=refid).one()
            host_id = host.id
            assert len(hosts._live_certificates_of_key(host)) == 2
        real, calls = SSHCertificateService.revoke_certificate, []

        def second_fails(cert_id, *args, **kwargs):
            calls.append(cert_id)
            if len(calls) == 2:
                raise OperationalError('UPDATE', {}, Exception('database is locked'))
            return real(cert_id, *args, **kwargs)
        monkeypatch.setattr(SSHCertificateService, 'revoke_certificate', second_fails)
        cut = _since(app)
        with app.app_context():
            with pytest.raises(OperationalError):
                hosts.revoke_host(host_id, 'key compromised', 'admin')
            db.session.rollback()
        monkeypatch.undo()
        # Who revoked it and why survive the cut: audited with revoked_at, before the sweep
        assert _audits(app, cut, 'ssh_host_revoked') == [(True, 'SSH host revoked, renewals ended: key compromised')]
        since = _since(app)
        # The host already shows revoked: the next request still sweeps what the first one left
        assert post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/revoke', {}).status_code == 200
        with app.app_context():
            assert hosts._live_certificates_of_key(db.session.get(SSHHost, host_id)) == []
        # The revocation itself is the request that set revoked_at: this one only finished it
        assert _audits(app, since, 'ssh_host_revoked') == []
        with app.app_context():
            done = AuditLog.query.filter(AuditLog.id > since, AuditLog.action == 'ssh_host_revocation_finished').all()
            assert [(a.username, a.resource_id) for a in done] == [('admin', str(host_id))]
        assert post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/revoke', {}).status_code == 409

    def test_a_renewal_left_live_by_a_failure_goes_with_the_sweep(self, app, auth_client, client,
                                                                            enrolled, tmp_path, monkeypatch,
                                                                            caplog):
        from sqlalchemy.exc import OperationalError
        from services.ssh_cert import SSHCertificateService
        _, refid, key = enrolled
        _age(app, refid)
        challenge = _challenge(client, refid).get_json()['challenge']
        with app.app_context():
            host_id = SSHHost.query.filter_by(refid=refid).one().id
        real = SSHCertificateService.sign_certificate

        def locked(*args, **kwargs):
            raise OperationalError('UPDATE', {}, Exception('database is locked'))

        def revoked_first(*args, **kwargs):
            hosts.revoke_host(host_id)
            monkeypatch.setattr(SSHCertificateService, 'revoke_certificate', locked)
            return real(*args, **kwargs)
        monkeypatch.setattr(SSHCertificateService, 'sign_certificate', revoked_first)
        with caplog.at_level('ERROR', logger=hosts.logger.name):
            r = _renew(client, refid, challenge, _sign(tmp_path, key, challenge))
        assert r.status_code == 403 and r.get_json()['state'] == 'revoked'
        assert any(rec.levelname == 'ERROR' and 'sweep will revoke it' in rec.getMessage() for rec in caplog.records)
        monkeypatch.undo()
        monkeypatch.setattr(hosts, 'REVOKED_HOST_GRACE_SECONDS', 0, raising=False)  # the task's grace is over
        with app.app_context():
            renewed = SSHCertificate.query.filter(SSHCertificate.ssh_ca_id == enrolled[0]['id'],
                                                  SSHCertificate.source == 'renewal').one()
            assert not renewed.revoked
            renewed_id = renewed.id
            # Signed after the revocation, by the host's own renewal: the sweep owes it to the KRL
            assert hosts.sweep_revoked_hosts() >= 1
            assert db.session.get(SSHCertificate, renewed_id).revoked

    def test_an_expired_certificate_cannot_renew(self, app, client, enrolled):
        _, refid, _ = enrolled
        with app.app_context():
            SSHHost.query.filter_by(refid=refid).one().certificate.valid_to = utc_now() - timedelta(seconds=1)
            db.session.commit()
        r = _challenge(client, refid)
        assert r.status_code == 403 and r.get_json()['state'] == 'expired'


class TestTheKrlPullIsSeen:
    def test_a_krl_download_naming_the_host_is_recorded_once_a_minute(self, app, auth_client, client, enrolled):
        user_ca = _create_ssh_ca(auth_client, descr='Renewal KRL seen CA')
        _, refid, _ = enrolled
        client.get(f"/ssh/krl/{user_ca['refid']}?host={refid}")
        with app.app_context():
            first = SSHHost.query.filter_by(refid=refid).one().last_krl_sync_at
        assert first is not None
        client.get(f"/ssh/krl/{user_ca['refid']}?host={refid}")
        with app.app_context():
            assert SSHHost.query.filter_by(refid=refid).one().last_krl_sync_at == first
        # Unnamed or unknown: nothing to record, the KRL is served all the same
        assert client.get(f"/ssh/krl/{user_ca['refid']}?host=';drop").status_code == 200


def _cut_short(app, client, refid, key, tmp_path, monkeypatch):
    """The host renewed once, then its revocation interrupted after the first of its two certificates."""
    from sqlalchemy.exc import OperationalError
    from services.ssh_cert import SSHCertificateService
    _age(app, refid)
    challenge = _challenge(client, refid).get_json()['challenge']
    assert _renew(client, refid, challenge, _sign(tmp_path, key, challenge)).status_code == 200
    with app.app_context():
        host = SSHHost.query.filter_by(refid=refid).one()
        host_id = host.id
        certs = [db.session.get(SSHCertificate, i).certificate for i in hosts._live_certificates_of_key(host)]
    assert len(certs) == 2
    real, calls = SSHCertificateService.revoke_certificate, []

    def second_fails(cert_id, *args, **kwargs):
        calls.append(cert_id)
        if len(calls) == 2:
            raise OperationalError('UPDATE', {}, Exception('database is locked'))
        return real(cert_id, *args, **kwargs)
    monkeypatch.setattr(SSHCertificateService, 'revoke_certificate', second_fails)
    with app.app_context():
        with pytest.raises(OperationalError):
            hosts.revoke_host(host_id)
        db.session.rollback()
    monkeypatch.undo()
    return host_id, certs


def _enroll_again(app, auth_client, client, tmp_path, ca, key, principals):
    token = post_json(auth_client, '/api/v2/ssh/enrollment-tokens', {
        'ca_id': ca['id'], 'principals': principals, 'validity_seconds': 86400}).get_json()['data']['token']
    r = client.post(f"/ssh/enroll/{ca['refid']}", data=json.dumps({
        'token': token, 'public_key': (tmp_path / 'ssh_host_ed25519_key.pub').read_text(),
        'signature': _sign(tmp_path, key, token, hosts.ENROLL_NAMESPACE)}), content_type='application/json')
    assert r.status_code == 201, r.data
    with app.app_context():
        host = SSHHost.query.filter_by(refid=r.get_json()['host_refid']).one()
        return host.id, host.certificate_id


def _in_krl(client, tmp_path, ca, cert_line):
    (tmp_path / 'krl').write_bytes(client.get(f"/ssh/krl/{ca['refid']}").data)
    (tmp_path / 'q-cert.pub').write_text(cert_line)
    out = subprocess.run(['ssh-keygen', '-Q', '-f', str(tmp_path / 'krl'), str(tmp_path / 'q-cert.pub')],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode in (0, 1), out.stdout + out.stderr
    return out.returncode == 1


class TestTheSweepOfRevokedHosts:
    @pytest.fixture(autouse=True)
    def _no_grace(self):
        # The revocations here are cut short in the past: the task's grace is over. A patch of its
        # own, which the tests' monkeypatch.undo() leaves in place
        patch = pytest.MonkeyPatch()
        patch.setattr(hosts, 'REVOKED_HOST_GRACE_SECONDS', 0, raising=False)
        yield
        patch.undo()

    def test_the_task_is_registered_at_its_interval(self, app):
        task = app.scheduler.tasks['ssh_revoked_host_sweep']
        assert task.func is hosts.sweep_revoked_hosts and task.interval == hosts.REVOKED_HOST_SWEEP_SECONDS

    def test_a_revocation_cut_short_is_finished_by_the_sweep(self, app, client, enrolled, tmp_path, monkeypatch):
        ca, refid, key = enrolled
        host_id, certs = _cut_short(app, client, refid, key, tmp_path, monkeypatch)
        assert not all(_in_krl(client, tmp_path, ca, c) for c in certs)
        since = _since(app)

        def finished():
            return [(a.username, a.details) for a in AuditLog.query.filter(
                AuditLog.id > since, AuditLog.action == 'ssh_host_revocation_finished',
                AuditLog.resource_id == str(host_id))]
        with app.app_context():
            hosts.sweep_revoked_hosts()
            assert hosts._live_certificates_of_key(db.session.get(SSHHost, host_id)) == []
        assert all(_in_krl(client, tmp_path, ca, c) for c in certs)
        with app.app_context():
            assert [u for u, _ in finished()] == ['system'] and '1 certificate' in finished()[0][1]
            # Nothing left: the next pass revokes nothing and writes nothing
            hosts.sweep_revoked_hosts()
            assert len(finished()) == 1

    def test_the_certificates_of_the_key_enrolled_again_stay_valid(self, app, auth_client, client, enrolled,
                                                                    tmp_path, monkeypatch):
        ca, refid, key = enrolled
        host_id, certs = _cut_short(app, client, refid, key, tmp_path, monkeypatch)
        again, _ = _enroll_again(app, auth_client, client, tmp_path, ca, key, ['db01.example.com'])
        with app.app_context():
            again_refid = db.session.get(SSHHost, again).refid
        # The new host renews too: its renewal certificate is its own, not the revoked host's. Its
        # timeline moved back as a whole, the revoked host's before it, for its renewal to be due
        with app.app_context():
            revoked, host = db.session.get(SSHHost, host_id), db.session.get(SSHHost, again)
            revoked.enrolled_at -= timedelta(days=20)
            revoked.revoked_at -= timedelta(days=20)
            for cert_id in set(hosts._live_certificates_of_key(revoked)) - {host.certificate_id}:
                db.session.get(SSHCertificate, cert_id).created_at -= timedelta(days=20)
            host.certificate.created_at -= timedelta(days=10)
            host.enrolled_at -= timedelta(days=10)
            db.session.commit()
        challenge = _challenge(client, again_refid).get_json()['challenge']
        assert _renew(client, again_refid, challenge, _sign(tmp_path, key, challenge)).status_code == 200
        with app.app_context():
            hosts.sweep_revoked_hosts()
            kept = hosts._live_certificates_of_key(db.session.get(SSHHost, again))
            assert len(kept) == 2
            kept_lines = [db.session.get(SSHCertificate, i).certificate for i in kept]
        assert all(_in_krl(client, tmp_path, ca, c) for c in certs)
        assert not any(_in_krl(client, tmp_path, ca, c) for c in kept_lines)

    def test_a_certificate_signed_for_the_key_after_its_revocation_is_left_alone(self, app, auth_client, enrolled):
        from services.ssh_cert import SSHCertificateService
        _, refid, _ = enrolled
        with app.app_context():
            host = SSHHost.query.filter_by(refid=refid).one()
            host_id, ca_id, line = host.id, host.ssh_ca_id, host.public_key
        assert post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/revoke', {}).status_code == 200
        with app.app_context():
            manual = SSHCertificateService.sign_certificate(
                ca_id=ca_id, public_key_data=line, cert_type='host', principals=['web01'],
                validity_seconds=3600, descr='signed by hand', source='web', username='admin').id
            hosts.sweep_revoked_hosts()
            assert not db.session.get(SSHCertificate, manual).revoked

    def test_revoking_again_after_the_key_was_enrolled_again_sweeps_only_the_old_host(self, app, auth_client,
                                                                                      client, enrolled, tmp_path,
                                                                                      monkeypatch):
        ca, refid, key = enrolled
        host_id, certs = _cut_short(app, client, refid, key, tmp_path, monkeypatch)
        _, kept = _enroll_again(app, auth_client, client, tmp_path, ca, key, ['db01.example.com'])
        assert post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/revoke', {}).status_code == 200
        assert all(_in_krl(client, tmp_path, ca, c) for c in certs)
        with app.app_context():
            assert not db.session.get(SSHCertificate, kept).revoked
        assert post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/revoke', {}).status_code == 409


class TestWhoFinishesARevocation:
    def test_the_task_leaves_a_revocation_in_its_grace_to_its_request(self, app, auth_client, enrolled,
                                                                      monkeypatch):
        """The task running between revoked_at and the request's own sweep finishes nothing in its name."""
        from services.ssh_cert import SSHCertificateService
        _, refid, _ = enrolled
        with app.app_context():
            host = SSHHost.query.filter_by(refid=refid).one()
            host_id, cert_id = host.id, host.certificate_id
        real, ran = SSHCertificateService.revoke_certificate, []

        def task_first(cert, *args, **kwargs):
            if not ran:
                ran.append(None)
                ran[0] = hosts.sweep_revoked_hosts()
            return real(cert, *args, **kwargs)
        monkeypatch.setattr(SSHCertificateService, 'revoke_certificate', task_first)
        since = _since(app)
        assert post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/revoke', {}).status_code == 200
        assert ran == [0]
        assert _audits(app, since, 'ssh_host_revocation_finished') == []
        with app.app_context():
            cert = db.session.get(SSHCertificate, cert_id)
            assert cert.revoked
            done = AuditLog.query.filter(AuditLog.id > since, AuditLog.action == 'ssh_host_revoked').all()
            assert [(a.username, a.resource_id) for a in done] == [('admin', str(host_id))]

    def test_a_certificate_goes_with_the_host_enrolled_when_it_was_signed(self, app, auth_client, tmp_path,
                                                                           monkeypatch):
        """A key enrolled as A, revoked, enrolled again as B whose revocation was cut short: B's left."""
        from services.ssh_cert import SSHCertificateService
        monkeypatch.setattr(hosts, 'REVOKED_HOST_GRACE_SECONDS', 0, raising=False)
        ca = _create_ssh_ca(auth_client, ca_type='host', descr=f'Owner CA {tmp_path.name}')
        key = tmp_path / 'owner_key'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
        line = (tmp_path / 'owner_key.pub').read_text().strip()
        now = utc_now()

        def signed(source, created):
            cert = SSHCertificateService.sign_certificate(
                ca_id=ca['id'], public_key_data=line, cert_type='host', principals=['owner01'],
                validity_seconds=86400, descr='owner', source=source, username='t')
            cert.created_at = created
            db.session.commit()
            return cert

        def host(name, cert, enrolled_at):
            row = SSHHost(ssh_ca_id=ca['id'], name=name, principals='["owner01"]', public_key=line,
                          key_type='ed25519', fingerprint=cert.fingerprint, certificate_id=cert.id,
                          auto_renew=True, enrolled_at=enrolled_at)
            db.session.add(row)
            db.session.commit()
            return row

        with app.app_context():
            a = host(f'owner-a-{tmp_path.name}', signed('enrollment', now - timedelta(hours=3)),
                     now - timedelta(hours=3))
            hosts.revoke_host(a.id)
            a = db.session.get(SSHHost, a.id)
            a.revoked_at = now - timedelta(hours=2)
            b = host(f'owner-b-{tmp_path.name}', signed('enrollment', now - timedelta(minutes=59)),
                     now - timedelta(hours=1))
            b.certificate_id = signed('renewal', now - timedelta(minutes=30)).id
            # Revoked, its sweep cut short before either certificate
            b.revoked_at, b.auto_renew = now - timedelta(minutes=20), False
            db.session.commit()
            a_id, b_id = a.id, b.id
        since = _since(app)
        with app.app_context():
            assert hosts.sweep_revoked_hosts() == 2
            done = AuditLog.query.filter(AuditLog.id > since,
                                         AuditLog.action == 'ssh_host_revocation_finished').all()
            assert [(a.resource_id, '2 certificate' in a.details) for a in done] == [(str(b_id), True)]
            assert a_id != b_id
