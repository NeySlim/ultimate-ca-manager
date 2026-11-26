"""SSH host enrollment (issue #451): an administrator creates a single-use, short-lived token for a
host CA and a list of host names; the host exchanges it once, at /ssh/enroll/<refid>, for a host
certificate of its own public key, for names the token allows. Every enrollment and refusal is
audited; revoking the host revokes its certificate and ends its renewals."""
import json
import shutil
import subprocess
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import ssh as ssh_ser

from models import AuditLog, db
from models.ssh import SSHCertificate, SSHHost, SSHHostEnrollmentToken
from services import ssh_host_service as hosts
from utils.datetime_utils import utc_now
from tests.test_ssh import _create_ssh_ca, post_json
from tests import sshsig_support
from tests.ssh_cleanup import ssh_rows_stay_in_their_module  # noqa: F401


# The private key of each public line _host_key made: _enroll signs the token with it
_PRIVATE = {}


def _host_key():
    private, public = sshsig_support.new_key()
    _PRIVATE[public] = private
    return public


def _host_ca(auth_client, descr, **extra):
    return _create_ssh_ca(auth_client, ca_type='host', descr=descr, **extra)


def _token(auth_client, ca, principals=('web01.example.com', 'web01'), **extra):
    r = post_json(auth_client, '/api/v2/ssh/enrollment-tokens',
                  {'ca_id': ca['id'], 'principals': list(principals), **extra})
    assert r.status_code == 201, r.data
    return r.get_json()['data']


def _enroll(client, ca, token, key=None, principals=None, text=False, signature=True):
    """*signature* True: the token signed with the host key, as the agent does; None: no proof."""
    key = key or _host_key()
    body = {'token': token, 'public_key': key}
    if signature is True and key in _PRIVATE and isinstance(token, str):
        signature = sshsig_support.sign(_PRIVATE[key], token, hosts.ENROLL_NAMESPACE)
    if isinstance(signature, str):
        body['signature'] = signature
    if principals is not None:
        body['principals'] = principals
    headers = {'Accept': 'text/plain'} if text else {}
    return client.post(f"/ssh/enroll/{ca['refid']}", data=json.dumps(body), content_type='application/json',
                       headers=headers)


def _audits(app, action, since):
    with app.app_context():
        return [(a.success, a.details) for a in AuditLog.query.filter(AuditLog.id > since, AuditLog.action == action)]


def _last_audit(app):
    with app.app_context():
        return db.session.query(db.func.max(AuditLog.id)).scalar() or 0


class TestTokens:
    def test_the_token_is_shown_once_and_stored_hashed(self, app, auth_client):
        ca = _host_ca(auth_client, 'Token shown once CA')
        token = _token(auth_client, ca)
        assert token['token'].startswith('ucmh_') and token['state'] == 'active'
        listed = auth_client.get(f"/api/v2/ssh/enrollment-tokens?ca_id={ca['id']}").get_json()['data']
        assert [t['id'] for t in listed] == [token['id']]
        assert 'token' not in listed[0] and token['token'] not in json.dumps(listed)
        with app.app_context():
            row = db.session.get(SSHHostEnrollmentToken, token['id'])
            assert row.token_hash == hosts.hash_token(token['token']) and token['token'] not in row.token_hash

    @pytest.mark.parametrize('body,status', [
        ({'principals': ['bad name']}, 400),
        ({'principals': []}, 400),
        ({'principals': ['a.example.com'], 'lifetime_seconds': 60}, 400),
        ({'principals': ['a.example.com'], 'lifetime_seconds': 8 * 86400}, 400),
        ({'principals': ['a.example.com'], 'renew_percent': 95}, 400),
        ({'principals': ['a.example.com'], 'validity_seconds': 10}, 400),
        ({'principals': ['a.example.com'], 'validity_seconds': '3600'}, 400),
    ])
    def test_its_fields_are_checked(self, auth_client, body, status):
        ca = _host_ca(auth_client, f'Token fields CA {status}')
        r = post_json(auth_client, '/api/v2/ssh/enrollment-tokens', {'ca_id': ca['id'], **body})
        assert r.status_code == status, r.data

    def test_a_user_ca_or_a_name_outside_the_ca_is_refused(self, auth_client):
        user_ca = _create_ssh_ca(auth_client, descr='Token user CA')
        assert post_json(auth_client, '/api/v2/ssh/enrollment-tokens',
                         {'ca_id': user_ca['id'], 'principals': ['a']}).status_code == 400
        narrow = _host_ca(auth_client, 'Token narrow CA', allow_any_principal=False,
                          allowed_principals=['*.prod.example.com'])
        r = post_json(auth_client, '/api/v2/ssh/enrollment-tokens',
                      {'ca_id': narrow['id'], 'principals': ['db.test.example.com']})
        assert r.status_code == 400 and 'allowed principals' in r.get_json()['message']
        assert post_json(auth_client, '/api/v2/ssh/enrollment-tokens',
                         {'ca_id': 999999, 'principals': ['a']}).status_code == 404

    def test_a_viewer_lists_but_cannot_create(self, auth_client, viewer_client):
        ca = _host_ca(auth_client, 'Token viewer CA')
        assert viewer_client.get('/api/v2/ssh/enrollment-tokens').status_code == 200
        assert post_json(viewer_client, '/api/v2/ssh/enrollment-tokens',
                         {'ca_id': ca['id'], 'principals': ['a']}).status_code == 403

    def test_a_revoked_token_cannot_enroll(self, app, auth_client, client):
        ca = _host_ca(auth_client, 'Token revoked CA')
        token = _token(auth_client, ca)
        r = auth_client.post(f"/api/v2/ssh/enrollment-tokens/{token['id']}/revoke")
        assert r.status_code == 200 and r.get_json()['data']['state'] == 'revoked'
        assert auth_client.post(f"/api/v2/ssh/enrollment-tokens/{token['id']}/revoke").status_code == 409
        since = _last_audit(app)
        assert _enroll(client, ca, token['token']).status_code == 403
        assert _audits(app, 'ssh_host_enrollment_refused', since) == [
            (False, f"SSH host enrollment refused: token {token['token_prefix']} is revoked")]


class TestEnrollment:
    def test_the_token_buys_one_host_certificate_of_the_host_key(self, app, auth_client, client, tmp_path):
        ca = _host_ca(auth_client, 'Enroll CA')
        token = _token(auth_client, ca, validity_seconds=7200)
        key = _host_key()
        since = _last_audit(app)
        r = _enroll(client, ca, token['token'], key)
        assert r.status_code == 201, r.data
        body = r.get_json()
        cert = ssh_ser.load_ssh_public_identity(body['certificate'].encode())
        assert cert.type == ssh_ser.SSHCertificateType.HOST
        assert cert.valid_principals == [b'web01.example.com', b'web01']
        assert ssh_ser.serialize_ssh_public_key(cert.public_key()).decode() == key
        assert 7100 < cert.valid_before - cert.valid_after - 300 <= 7200
        with app.app_context():
            host = SSHHost.query.filter_by(refid=body['host_refid']).one()
            assert host.name == 'web01.example.com' and host.certificate.certificate == body['certificate']
            assert host.state == 'valid' and host.auto_renew
            spent = db.session.get(SSHHostEnrollmentToken, token['id'])
            assert spent.state == 'used' and spent.used_by_host_id == host.id
        [(ok, details)] = _audits(app, 'ssh_host_enrolled', since)
        assert ok and 'web01.example.com, web01' in details
        # Single use
        assert _enroll(client, ca, token['token']).status_code == 403

    def test_text_plain_answers_in_lines(self, auth_client, client):
        ca = _host_ca(auth_client, 'Enroll text CA')
        r = _enroll(client, ca, _token(auth_client, ca)['token'], text=True)
        assert r.status_code == 201 and r.mimetype == 'text/plain'
        fields = dict(line.split('=', 1) for line in r.data.decode().splitlines())
        assert fields['certificate'].startswith('ssh-ed25519-cert-v01@openssh.com ')
        assert fields['principals'] == 'web01.example.com,web01' and fields['renew_percent'] == '30'

    def test_a_subset_of_the_names_is_signed_and_others_are_refused(self, auth_client, client):
        ca = _host_ca(auth_client, 'Enroll subset CA')
        r = _enroll(client, ca, _token(auth_client, ca)['token'], principals=['web01'])
        assert r.status_code == 201
        cert = ssh_ser.load_ssh_public_identity(r.get_json()['certificate'].encode())
        assert cert.valid_principals == [b'web01']
        r = _enroll(client, ca, _token(auth_client, ca)['token'], principals=['web01', 'db01'])
        assert r.status_code == 403 and 'db01' in r.get_json()['error']

    @pytest.mark.parametrize('kind', ['text', 'certificate', 'rsa1024'])
    def test_a_bad_key_is_refused_before_the_token_is_spent(self, app, auth_client, client, kind):
        key = {'text': 'not a key', 'certificate': 'ssh-ed25519-cert-v01@openssh.com AAAA',
               'rsa1024': ssh_ser.serialize_ssh_public_key(
                   rsa.generate_private_key(65537, 1024).public_key()).decode()}[kind]
        ca = _host_ca(auth_client, f'Enroll bad key CA {kind}')
        token = _token(auth_client, ca)
        assert _enroll(client, ca, token['token'], key).status_code == 400
        with app.app_context():
            assert db.session.get(SSHHostEnrollmentToken, token['id']).state == 'active'

    def test_an_expired_token_or_one_of_another_ca_is_refused(self, app, auth_client, client):
        ca, other = _host_ca(auth_client, 'Enroll expired CA'), _host_ca(auth_client, 'Enroll other CA')
        expired, foreign = _token(auth_client, ca), _token(auth_client, other)
        with app.app_context():
            db.session.get(SSHHostEnrollmentToken, expired['id']).expires_at = utc_now() - timedelta(seconds=1)
            db.session.commit()
        since = _last_audit(app)
        assert _enroll(client, ca, expired['token']).status_code == 403
        assert _enroll(client, ca, foreign['token']).status_code == 403
        assert _enroll(client, ca, 'ucmh_' + 'x' * 43).status_code == 403
        assert _enroll(client, ca, 'garbage').status_code == 403
        reasons = [d for _, d in _audits(app, 'ssh_host_enrollment_refused', since)]
        assert reasons == [f"SSH host enrollment refused: token {expired['token_prefix']} is expired",
                           f"SSH host enrollment refused: token {foreign['token_prefix']} is for another CA",
                           'SSH host enrollment refused: unknown token',
                           'SSH host enrollment refused: malformed token']

    def test_two_exchanges_of_one_token_sign_once(self, app, auth_client, client, monkeypatch):
        ca = _host_ca(auth_client, 'Enroll race CA')
        token = _token(auth_client, ca)
        real = hosts.checked_host_key

        def other_exchange_first(public_key):
            # The other request spends the token between this one's checks and its write
            with app.app_context():
                db.session.get(SSHHostEnrollmentToken, token['id']).used_at = utc_now()
                db.session.commit()
            return real(public_key)
        monkeypatch.setattr(hosts, 'checked_host_key', other_exchange_first)
        with app.app_context():
            before = SSHCertificate.query.filter_by(ssh_ca_id=ca['id']).count()
        assert _enroll(client, ca, token['token']).status_code == 403
        with app.app_context():
            assert SSHCertificate.query.filter_by(ssh_ca_id=ca['id']).count() == before

    def test_the_same_key_enrolled_again_for_the_same_names_keeps_its_host(self, app, auth_client, client):
        ca = _host_ca(auth_client, 'Enroll again CA')
        key = _host_key()
        first = _enroll(client, ca, _token(auth_client, ca)['token'], key).get_json()
        second = _enroll(client, ca, _token(auth_client, ca)['token'], key)
        assert second.status_code == 201 and second.get_json()['host_refid'] == first['host_refid']

    def test_the_same_names_in_another_order_keep_its_host(self, app, auth_client, client):
        ca = _host_ca(auth_client, 'Enroll reordered CA')
        key = _host_key()
        first = _enroll(client, ca, _token(auth_client, ca)['token'], key).get_json()
        again = _token(auth_client, ca, principals=['web01', 'web01.example.com'])
        r = _enroll(client, ca, again['token'], key)
        assert r.status_code == 201, r.data
        assert r.get_json()['host_refid'] == first['host_refid']

    def test_the_same_key_for_other_names_is_409_until_its_host_is_revoked(self, app, auth_client, client):
        ca = _host_ca(auth_client, 'Enroll other names CA')
        key = _host_key()
        first = _enroll(client, ca, _token(auth_client, ca)['token'], key).get_json()
        token = _token(auth_client, ca, principals=['web02'])
        r = _enroll(client, ca, token['token'], key)
        assert r.status_code == 409 and 'revoke' in r.get_json()['error']
        with app.app_context():
            host = SSHHost.query.filter_by(refid=first['host_refid']).one()
            assert host.get_principals() == ['web01.example.com', 'web01']
            assert db.session.get(SSHHostEnrollmentToken, token['id']).state == 'active'
            host_id = host.id
        assert post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/revoke', {}).status_code == 200
        r = _enroll(client, ca, token['token'], key)
        assert r.status_code == 201 and r.get_json()['host_refid'] != first['host_refid']
        # The old host revoked again leaves the certificate of the key's new host alone
        assert post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/revoke', {}).status_code == 409
        with app.app_context():
            assert not SSHHost.query.filter_by(refid=r.get_json()['host_refid']).one().certificate.revoked


    def test_a_certificate_the_ca_refuses_leaves_the_token_unspent(self, app, auth_client, client):
        from models.ssh import SSHCertificateAuthority
        ca = _host_ca(auth_client, 'Enroll narrowed CA')
        token = _token(auth_client, ca)
        # The CA narrowed after the token was made: its signature refuses the names
        with app.app_context():
            row = db.session.get(SSHCertificateAuthority, ca['id'])
            row.allow_any_principal = False
            row.set_allowed_principals(['*.prod.example.com'])
            db.session.commit()
        r = _enroll(client, ca, token['token'])
        assert r.status_code == 400 and 'allowed principals' in r.get_json()['error']
        with app.app_context():
            assert db.session.get(SSHHostEnrollmentToken, token['id']).state == 'active'

    @pytest.mark.parametrize('failure', ['serial', 'storage'])
    def test_any_signing_failure_gives_the_token_back(self, app, auth_client, client, monkeypatch, failure):
        from services.ssh_cert import SSHCertificateService
        from services.ssh_cert.signing import SSHSerialConflict
        ca = _host_ca(auth_client, f'Enroll {failure} failure CA')
        token = _token(auth_client, ca)
        error = SSHSerialConflict('try again') if failure == 'serial' else RuntimeError('disk full')

        def failing(*args, **kwargs):
            raise error
        monkeypatch.setattr(SSHCertificateService, 'sign_certificate', failing)
        key = _host_key()
        signature = sshsig_support.sign(_PRIVATE[key], token['token'], hosts.ENROLL_NAMESPACE)
        with app.app_context():
            with pytest.raises(type(error)):
                hosts.enroll(ca['refid'], token['token'], key, signature=signature)
            assert db.session.get(SSHHostEnrollmentToken, token['id']).state == 'active'
        monkeypatch.undo()
        assert _enroll(client, ca, token['token'], key).status_code == 201

    def test_a_failed_give_back_keeps_the_signing_error(self, app, auth_client, client, monkeypatch, caplog):
        from sqlalchemy.exc import OperationalError
        from services.ssh_cert import SSHCertificateService
        ca = _host_ca(auth_client, 'Enroll give-back failure CA')
        token = _token(auth_client, ca)

        def lost(*args, **kwargs):
            raise OperationalError('UPDATE', {}, Exception('server closed the connection'))

        def failing(*args, **kwargs):
            monkeypatch.setattr(db.session, 'execute', lost)
            raise RuntimeError('disk full')
        monkeypatch.setattr(SSHCertificateService, 'sign_certificate', failing)
        key = _host_key()
        signature = sshsig_support.sign(_PRIVATE[key], token['token'], hosts.ENROLL_NAMESPACE)
        with app.app_context():
            with caplog.at_level('ERROR', logger=hosts.logger.name):
                with pytest.raises(RuntimeError, match='disk full'):
                    hosts.enroll(ca['refid'], token['token'], key, signature=signature)
            monkeypatch.undo()
            db.session.rollback()
        assert any(rec.levelname == 'ERROR' and token['token_prefix'] in rec.getMessage()
                   for rec in caplog.records)


class TestProofOfPossession:
    """The token signed with the host key: a public key alone, which any server shows, enrolls nothing."""

    def test_another_servers_public_key_cannot_take_its_host(self, app, auth_client, client):
        ca = _host_ca(auth_client, 'Enroll victim CA')
        victim = _host_key()
        first = _enroll(client, ca, _token(auth_client, ca)['token'], victim).get_json()
        evil = _token(auth_client, ca, principals=['evil.example.com'])
        attacker, _ = sshsig_support.new_key()
        since = _last_audit(app)
        assert _enroll(client, ca, evil['token'], victim, signature=None).status_code == 403
        forged = sshsig_support.sign(attacker, evil['token'], hosts.ENROLL_NAMESPACE)
        assert _enroll(client, ca, evil['token'], victim, signature=forged).status_code == 403
        with app.app_context():
            host = SSHHost.query.filter_by(refid=first['host_refid']).one()
            assert host.name == 'web01.example.com' and host.get_principals() == ['web01.example.com', 'web01']
            assert db.session.get(SSHHostEnrollmentToken, evil['id']).state == 'active'
        assert [d for _, d in _audits(app, 'ssh_host_enrollment_refused', since)] == [
            'SSH host enrollment refused: no signature of the token by the host key',
            'SSH host enrollment refused: signed with another key']

    def test_a_signature_of_another_token_or_purpose_is_refused(self, app, auth_client, client):
        ca = _host_ca(auth_client, 'Enroll proof CA')
        key = _host_key()
        token, other = _token(auth_client, ca), _token(auth_client, ca)
        for signature in (sshsig_support.sign(_PRIVATE[key], other['token'], hosts.ENROLL_NAMESPACE),
                          sshsig_support.sign(_PRIVATE[key], token['token'], hosts.NAMESPACE),
                          'not a signature'):
            r = _enroll(client, ca, token['token'], key, signature=signature)
            assert r.status_code == 403 and r.get_json()['error'] == 'the signature does not prove the host key'
        with app.app_context():
            assert db.session.get(SSHHostEnrollmentToken, token['id']).state == 'active'
        assert _enroll(client, ca, token['token'], key).status_code == 201

    def test_an_unknown_ca_is_404_and_a_bad_body_400(self, auth_client, client):
        assert client.post('/ssh/enroll/nope', data='{}', content_type='application/json').status_code == 403
        ca = _host_ca(auth_client, 'Enroll body CA')
        assert client.post(f"/ssh/enroll/{ca['refid']}", data='[1]', content_type='application/json').status_code == 400
        assert _enroll(client, {'refid': 'nope'}, _token(auth_client, ca)['token']).status_code == 404


class TestHosts:
    def _enrolled(self, auth_client, client, descr):
        ca = _host_ca(auth_client, descr)
        r = _enroll(client, ca, _token(auth_client, ca)['token'])
        host = [h for h in auth_client.get(f"/api/v2/ssh/hosts?ca_id={ca['id']}").get_json()['data']
                if h['refid'] == r.get_json()['host_refid']][0]
        return ca, host

    @pytest.mark.skipif(not shutil.which('ssh-keygen'), reason='ssh-keygen not available')
    def test_revoking_the_host_revokes_its_certificate_in_the_krl(self, app, auth_client, client, tmp_path):
        ca, host = self._enrolled(auth_client, client, 'Hosts revoke CA')
        r = post_json(auth_client, f"/api/v2/ssh/hosts/{host['id']}/revoke", {'reason': 'decommissioned'})
        assert r.status_code == 200, r.data
        assert r.get_json()['data']['state'] == 'revoked' and not r.get_json()['data']['auto_renew']
        with app.app_context():
            cert = db.session.get(SSHCertificate, host['certificate_id'])
            assert cert.revoked and cert.revoke_reason == 'decommissioned'
            certificate = cert.certificate
        (tmp_path / 'krl').write_bytes(client.get(f"/ssh/krl/{ca['refid']}").data)
        (tmp_path / 'c').write_text(certificate)
        assert subprocess.run(['ssh-keygen', '-Q', '-f', str(tmp_path / 'krl'), str(tmp_path / 'c')]).returncode == 1
        assert post_json(auth_client, f"/api/v2/ssh/hosts/{host['id']}/revoke", {}).status_code == 409
        assert post_json(auth_client, f"/api/v2/ssh/hosts/{host['id']}/auto-renew", {'enabled': True}).status_code == 400

    def test_renewal_is_switched_off_and_on(self, auth_client, client):
        _, host = self._enrolled(auth_client, client, 'Hosts toggle CA')
        r = post_json(auth_client, f"/api/v2/ssh/hosts/{host['id']}/auto-renew", {'enabled': False})
        assert r.status_code == 200 and r.get_json()['data']['auto_renew'] is False
        r = post_json(auth_client, f"/api/v2/ssh/hosts/{host['id']}/auto-renew", {'enabled': True})
        assert r.get_json()['data']['auto_renew'] is True
        assert post_json(auth_client, f"/api/v2/ssh/hosts/{host['id']}/auto-renew", {'enabled': 'no'}).status_code == 400

    def test_the_list_counts_states_and_filters(self, auth_client, client):
        ca, host = self._enrolled(auth_client, client, 'Hosts list CA')
        _enroll(client, ca, _token(auth_client, ca, principals=['db01'])['token'])
        post_json(auth_client, f"/api/v2/ssh/hosts/{host['id']}/revoke", {})
        r = auth_client.get(f"/api/v2/ssh/hosts?ca_id={ca['id']}").get_json()
        assert r['meta']['counts'] == {'valid': 1, 'expired': 0, 'revoked': 1, 'total': 2}
        revoked = auth_client.get(f"/api/v2/ssh/hosts?ca_id={ca['id']}&state=revoked").get_json()['data']
        assert [h['id'] for h in revoked] == [host['id']]
        assert [h['name'] for h in auth_client.get(f"/api/v2/ssh/hosts?ca_id={ca['id']}&search=db0").get_json()['data']] == ['db01']
        assert auth_client.get('/api/v2/ssh/hosts?state=nope').status_code == 400
        assert auth_client.get('/api/v2/ssh/hosts/999999').status_code == 404

    def test_a_viewer_reads_hosts_but_cannot_revoke(self, auth_client, client, viewer_client):
        _, host = self._enrolled(auth_client, client, 'Hosts viewer CA')
        assert viewer_client.get(f"/api/v2/ssh/hosts/{host['id']}").status_code == 200
        assert post_json(viewer_client, f"/api/v2/ssh/hosts/{host['id']}/revoke", {}).status_code == 403
        assert post_json(viewer_client, f"/api/v2/ssh/hosts/{host['id']}/auto-renew", {'enabled': False}).status_code == 403
