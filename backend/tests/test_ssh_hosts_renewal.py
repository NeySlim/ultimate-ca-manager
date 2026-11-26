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
        return [(a.success, a.details) for a in AuditLog.query.filter(AuditLog.id > since, AuditLog.action == action)]


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
