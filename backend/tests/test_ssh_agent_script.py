"""The SSH agent of issue #451, run under a prefix against a live UCM: the installer puts the KRL
in place before sshd reads it, a sync downloads only a changed KRL (ETag), checks it and swaps it
atomically, reloads sshd only when it changed, refuses an older or broken KRL, and the agent is
idempotent and removable. The installer holds no secret."""
import shutil
import subprocess

import pytest

from api.v2.ssh.agent_script import AGENT, shell_safe_base_url
from models import db
from models.ssh import SSHKRL
from tests.ssh_agent_support import AgentHost, live_server
from tests.test_ssh import _create_ssh_ca, _generate_test_ssh_key, post_json
from tests.ssh_cleanup import ssh_rows_stay_in_their_module  # noqa: F401

pytestmark = pytest.mark.skipif(not shutil.which('ssh-keygen'), reason='ssh-keygen not available')

BEGIN = '# BEGIN ucm-ssh-agent'


@pytest.fixture
def host(tmp_path):
    h = AgentHost(tmp_path)
    yield h
    h.close()


@pytest.fixture
def server(app):
    with live_server(app) as url:
        yield url


def _installer(server, refid):
    import urllib.request
    with urllib.request.urlopen(f'{server}/ssh/setup/{refid}/agent', timeout=30) as resp:
        return resp.read().decode()


def _krl_version(path):
    out = subprocess.run(['ssh-keygen', '-Q', '-l', '-f', str(path)], capture_output=True, text=True)
    return int(next(line for line in out.stdout.splitlines() if line.startswith('# KRL version')).split()[-1])


def _issue_and_revoke(auth_client, ca):
    r = post_json(auth_client, '/api/v2/ssh/certificates', {
        'ca_id': ca['id'], 'public_key': _generate_test_ssh_key(), 'cert_type': 'user',
        'principals': ['bob'], 'validity_seconds': 3600})
    assert r.status_code == 201, r.data
    assert post_json(auth_client, f"/api/v2/ssh/certificates/{r.get_json()['data']['id']}/revoke",
                     {}).status_code == 200


class TestTheInstallerEndpoint:
    def test_an_unknown_ca_answers_a_failing_script(self, client):
        r = client.get('/ssh/setup/no-such-ca/agent')
        assert r.status_code == 404 and b'exit 1' in r.data

    def test_it_embeds_the_url_and_the_refid_and_nothing_secret(self, app, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Agent installer CA')
        r = app.test_client().get(f"/ssh/setup/{ca['refid']}/agent", base_url='https://ucm.example.com:8443')
        assert r.status_code == 200 and r.mimetype == 'text/x-shellscript'
        body = r.data.decode()
        assert "UCM_URL='https://ucm.example.com:8443'" in body
        assert f"CA_REFID='{ca['refid']}'" in body
        assert 'PRIVATE KEY' not in body and 'no-store' in r.headers['Cache-Control']
        assert subprocess.run(['sh', '-n'], input=body, text=True).returncode == 0

    def test_a_host_name_a_shell_would_read_is_refused(self, app, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Agent bad host CA')
        r = app.test_client().get(f"/ssh/setup/{ca['refid']}/agent", base_url="http://x';id;'")
        assert r.status_code == 400 and b'exit 1' in r.data

    @pytest.mark.parametrize('url,expected', [
        ('https://ucm.example.com:8443/', 'https://ucm.example.com:8443'),
        ('http://[2001:db8::1]:8443/', 'http://[2001:db8::1]:8443'),
        ('https://ucm.example.com/pki/', 'https://ucm.example.com/pki'),
        ('https://ucm.example.com/$(id)/', None),
        ('https://ucm`id`.example.com/', None),
        ("https://ucm.example.com/'/", None),
    ])
    def test_the_base_url_is_kept_only_when_shell_safe(self, url, expected):
        assert shell_safe_base_url(url) == expected


@pytest.mark.skipif(not shutil.which('shellcheck'), reason='shellcheck not available')
def test_the_agent_and_its_installer_pass_shellcheck(app, auth_client, tmp_path):
    ca = _create_ssh_ca(auth_client, descr='Agent shellcheck CA')
    installer = app.test_client().get(f"/ssh/setup/{ca['refid']}/agent").data.decode()
    for name, body in (('agent.sh', AGENT), ('installer.sh', installer)):
        (tmp_path / name).write_text(body)
        out = subprocess.run(['shellcheck', '-s', 'sh', str(tmp_path / name)], capture_output=True, text=True)
        assert out.returncode == 0, out.stdout


class TestTheAgent:
    def test_install_puts_the_krl_in_place_then_points_sshd_at_it(self, auth_client, host, server):
        ca = _create_ssh_ca(auth_client, descr='Agent install CA')
        out = host.install(_installer(server, ca['refid']))
        assert out.returncode == 0, out.stderr
        assert host.krl.read_bytes()[:6] == b'SSHKRL'
        config = (host.ssh / 'sshd_config').read_text()
        # At the top, ahead of the Match block a later line would fall into
        assert config.startswith(BEGIN)
        assert f'RevokedKeys {host.krl}\n' in config
        assert config.index('RevokedKeys') < config.index('Match User nobody')
        assert host.conf()['KRL_CA'] == ca['refid'] and host.conf()['UCM_URL'] == server
        assert host.agent.exists()

    def test_a_drop_in_directory_sshd_includes_takes_the_directive(self, auth_client, host, server):
        ca = _create_ssh_ca(auth_client, descr='Agent drop-in CA')
        (host.ssh / 'sshd_config.d').mkdir()
        main = 'Include /etc/ssh/sshd_config.d/*.conf\nPort 2222\n'
        (host.ssh / 'sshd_config').write_text(main)
        assert host.install(_installer(server, ca['refid'])).returncode == 0
        assert (host.ssh / 'sshd_config').read_text() == main
        assert f'RevokedKeys {host.krl}' in (host.ssh / 'sshd_config.d' / '40-ucm-ssh-agent.conf').read_text()

    def test_an_unchanged_krl_is_not_downloaded_again_nor_sshd_reloaded(self, auth_client, host, server, app):
        ca = _create_ssh_ca(auth_client, descr='Agent unchanged CA')
        assert host.install(_installer(server, ca['refid'])).returncode == 0
        before, hups = host.krl.stat().st_mtime_ns, host.hup_count()
        with app.app_context():
            # A 200 would carry these bytes: a 304 leaves the installed KRL alone
            row = db.session.get(SSHKRL, ca['id'])
            row.data = b'SSHKRL\n\0 not a KRL'
            db.session.commit()
        out = host.run('sync')
        assert out.returncode == 0, out.stderr
        assert host.krl.stat().st_mtime_ns == before and host.hup_count() == hups

    def test_a_revocation_reaches_the_server_at_the_next_sync(self, auth_client, host, server):
        ca = _create_ssh_ca(auth_client, descr='Agent revocation CA')
        assert host.install(_installer(server, ca['refid'])).returncode == 0
        first, hups = _krl_version(host.krl), host.hup_count()
        _issue_and_revoke(auth_client, ca)
        out = host.run('sync')
        assert out.returncode == 0, out.stderr
        assert _krl_version(host.krl) > first
        assert host.hup_count(hups + 1) == hups + 1
        assert f'KRL version {_krl_version(host.krl)} installed' in out.stderr

    def test_a_broken_krl_is_refused_and_the_installed_one_stays(self, auth_client, host, server, app):
        ca = _create_ssh_ca(auth_client, descr='Agent broken CA')
        assert host.install(_installer(server, ca['refid'])).returncode == 0
        installed = host.krl.read_bytes()
        with app.app_context():
            row = db.session.get(SSHKRL, ca['id'])
            row.data, row.version = b'SSHKRL\n\0' + b'\xff' * 40, row.version + 1
            db.session.commit()
        out = host.run('sync')
        assert out.returncode == 1 and 'not valid' in out.stderr
        assert host.krl.read_bytes() == installed
        assert not list(host.conf_dir.glob('.revoked_keys.*'))

    def test_an_older_krl_is_refused(self, auth_client, host, server, app, tmp_path):
        ca = _create_ssh_ca(auth_client, descr='Agent rollback CA')
        assert host.install(_installer(server, ca['refid'])).returncode == 0
        older = tmp_path / 'older.krl'
        subprocess.run(['ssh-keygen', '-k', '-z', '5', '-f', str(older)], check=True, capture_output=True)
        installed = host.krl.read_bytes()
        with app.app_context():
            row = db.session.get(SSHKRL, ca['id'])
            row.data, row.version = older.read_bytes(), row.version + 1
            db.session.commit()
        out = host.run('sync')
        assert out.returncode == 1 and 'refused KRL version 5' in out.stderr
        assert host.krl.read_bytes() == installed

    def test_a_failed_download_changes_nothing_at_install(self, auth_client, host, server):
        ca = _create_ssh_ca(auth_client, descr='Agent failed CA')
        script = _installer(server, ca['refid']).replace(ca['refid'], '00000000-0000-0000-0000-000000000000')
        out = host.install(script)
        assert out.returncode == 1
        assert BEGIN not in (host.ssh / 'sshd_config').read_text()
        assert not host.krl.exists()

    def test_sshd_refusing_the_settings_restores_sshd_config(self, auth_client, host, server, tmp_path):
        ca = _create_ssh_ca(auth_client, descr='Agent refused CA')
        original = (host.ssh / 'sshd_config').read_text()
        flag = tmp_path / 'fail'
        flag.write_text('')
        out = host.install(_installer(server, ca['refid']), env={'FAKE_SSHD_FAIL': str(flag)})
        assert out.returncode == 1 and 'restored' in out.stderr
        assert (host.ssh / 'sshd_config').read_text() == original

    def test_installing_twice_keeps_one_block(self, auth_client, host, server):
        ca = _create_ssh_ca(auth_client, descr='Agent twice CA')
        script = _installer(server, ca['refid'])
        assert host.install(script).returncode == 0
        assert host.install(script, '--interval', '5').returncode == 0
        assert (host.ssh / 'sshd_config').read_text().count(BEGIN) == 1
        assert host.conf()['INTERVAL'] == '5'

    def test_uninstall_removes_the_directive_then_the_files(self, auth_client, host, server):
        ca = _create_ssh_ca(auth_client, descr='Agent uninstall CA')
        original = (host.ssh / 'sshd_config').read_text()
        script = _installer(server, ca['refid'])
        assert host.install(script).returncode == 0
        out = host.install(script, '--uninstall')
        assert out.returncode == 0, out.stderr
        assert (host.ssh / 'sshd_config').read_text() == original
        assert not host.krl.exists() and not host.agent.exists() and not host.conf_dir.exists()

    def test_a_host_ca_is_refused(self, auth_client, host, server):
        ca = _create_ssh_ca(auth_client, ca_type='host', descr='Agent host-type CA')
        out = host.install(_installer(server, ca['refid']))
        assert out.returncode == 1 and 'host certificates' in out.stderr

    def test_the_interval_is_checked(self, auth_client, host, server):
        ca = _create_ssh_ca(auth_client, descr='Agent interval CA')
        out = host.install(_installer(server, ca['refid']), '--interval', '0;id')
        assert out.returncode == 1 and not host.agent.exists()



def _enroll_token(auth_client, ca, principals=('web01.example.com',), **extra):
    r = post_json(auth_client, '/api/v2/ssh/enrollment-tokens',
                  {'ca_id': ca['id'], 'principals': list(principals), **extra})
    assert r.status_code == 201, r.data
    return r.get_json()['data']['token']


class TestTheAgentEnrolls:
    def test_a_host_ca_needs_a_token(self, auth_client, host, server):
        ca = _create_ssh_ca(auth_client, ca_type='host', descr='Agent no token CA')
        out = host.install(_installer(server, ca['refid']))
        assert out.returncode == 1 and 'UCM_ENROLL_TOKEN' in out.stderr

    def test_the_token_buys_the_host_certificate_sshd_presents(self, app, auth_client, host, server):
        ca = _create_ssh_ca(auth_client, ca_type='host', descr='Agent enroll CA')
        token = _enroll_token(auth_client, ca, principals=('web01.example.com', 'web01'))
        out = host.install(_installer(server, ca['refid']), '--principal', 'web01',
                           env={'UCM_ENROLL_TOKEN': token})
        assert out.returncode == 0, out.stderr
        cert = host.ssh / 'ssh_host_ed25519_key-cert.pub'
        listed = subprocess.run(['ssh-keygen', '-L', '-f', str(cert)], capture_output=True, text=True).stdout
        assert 'host certificate' in listed and 'web01' in listed and 'web01.example.com' not in listed
        config = (host.ssh / 'sshd_config').read_text()
        assert config.startswith(BEGIN) and f'HostCertificate {cert}\n' in config
        conf = host.conf()
        assert conf['HOST_CA'] == ca['refid'] and conf['HOST_CERT'] == str(cert)
        with app.app_context():
            from models.ssh import SSHHost
            assert SSHHost.query.filter_by(refid=conf['HOST_REFID']).one().get_principals() == ['web01']
        # The token never reaches the disk
        assert not [p for p in host.root.rglob('*') if p.is_file() and token.encode() in p.read_bytes()]

    def test_a_refused_token_changes_nothing(self, auth_client, host, server):
        ca = _create_ssh_ca(auth_client, ca_type='host', descr='Agent refused token CA')
        original = (host.ssh / 'sshd_config').read_text()
        out = host.install(_installer(server, ca['refid']), env={'UCM_ENROLL_TOKEN': 'ucmh_' + 'A' * 43})
        assert out.returncode == 1 and 'HTTP 403' in out.stderr and 'invalid, used or expired' in out.stderr
        assert (host.ssh / 'sshd_config').read_text() == original
        assert not (host.ssh / 'ssh_host_ed25519_key-cert.pub').exists()

    def test_a_certificate_of_another_key_is_not_installed(self, auth_client, host, server, monkeypatch):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives.serialization import ssh as ssh_ser
        from services import ssh_host_service
        ca = _create_ssh_ca(auth_client, ca_type='host', descr='Agent other key CA')
        other = ssh_ser.serialize_ssh_public_key(ed25519.Ed25519PrivateKey.generate().public_key()).decode()
        real = ssh_host_service.checked_host_key
        monkeypatch.setattr(ssh_host_service, 'checked_host_key', lambda key: real(other))
        # A server that certifies another key than the one the agent proved
        from utils import sshsig
        monkeypatch.setattr(sshsig, 'verify', lambda *args: None)
        out = host.install(_installer(server, ca['refid']), env={'UCM_ENROLL_TOKEN': _enroll_token(auth_client, ca)})
        assert out.returncode == 1 and 'does not certify' in out.stderr
        assert not (host.ssh / 'ssh_host_ed25519_key-cert.pub').exists()

    def test_uninstall_puts_back_the_certificate_found_before(self, auth_client, host, server):
        ca = _create_ssh_ca(auth_client, ca_type='host', descr='Agent restore cert CA')
        cert = host.ssh / 'ssh_host_ed25519_key-cert.pub'
        cert.write_text('the certificate found there\n')
        original = (host.ssh / 'sshd_config').read_text()
        script = _installer(server, ca['refid'])
        assert host.install(script, env={'UCM_ENROLL_TOKEN': _enroll_token(auth_client, ca)}).returncode == 0
        assert cert.read_text() != 'the certificate found there\n'
        assert host.install(script, '--uninstall').returncode == 0
        assert cert.read_text() == 'the certificate found there\n'
        assert (host.ssh / 'sshd_config').read_text() == original

    def test_a_server_follows_a_krl_and_presents_a_host_certificate(self, auth_client, host, server):
        user_ca = _create_ssh_ca(auth_client, descr='Agent both user CA')
        host_ca = _create_ssh_ca(auth_client, ca_type='host', descr='Agent both host CA')
        assert host.install(_installer(server, user_ca['refid'])).returncode == 0
        assert host.install(_installer(server, host_ca['refid']),
                            env={'UCM_ENROLL_TOKEN': _enroll_token(auth_client, host_ca)}).returncode == 0
        config = (host.ssh / 'sshd_config').read_text()
        assert config.count(BEGIN) == 1 and 'RevokedKeys' in config and 'HostCertificate' in config


class TestTheAgentRenews:
    @pytest.fixture
    def enrolled_host(self, app, auth_client, host, server):
        ca = _create_ssh_ca(auth_client, ca_type='host', descr=f'Agent renew CA {host.root.parent.name}')
        out = host.install(_installer(server, ca['refid']), env={'UCM_ENROLL_TOKEN': _enroll_token(auth_client, ca)})
        assert out.returncode == 0, out.stderr
        return ca, host.conf()['HOST_REFID']

    def _age(self, app, refid):
        from datetime import timedelta
        from models.ssh import SSHHost
        from utils.datetime_utils import utc_now
        with app.app_context():
            cert = SSHHost.query.filter_by(refid=refid).one().certificate
            cert.created_at = utc_now() - timedelta(days=3650)
            db.session.commit()

    def _refusals(self, app):
        from models import AuditLog
        with app.app_context():
            return AuditLog.query.filter_by(action='ssh_host_renewal_refused').count()

    def test_a_certificate_in_its_last_share_is_renewed_and_sshd_reloaded(self, app, host, enrolled_host):
        _, refid = enrolled_host
        cert = host.ssh / 'ssh_host_ed25519_key-cert.pub'
        before, hups = cert.read_text(), host.hup_count()
        out = host.run('sync')
        assert out.returncode == 0, out.stderr
        assert cert.read_text() == before and host.hup_count() == hups
        self._age(app, refid)
        out = host.run('sync')
        assert out.returncode == 0, out.stderr
        assert 'host certificate renewed' in out.stderr
        assert cert.read_text() != before and host.hup_count(hups + 1) == hups + 1
        from models.ssh import SSHHost
        with app.app_context():
            assert SSHHost.query.filter_by(refid=refid).one().certificate.certificate == cert.read_text().strip()

    def test_a_revoked_host_stops_asking(self, app, auth_client, host, enrolled_host):
        from models.ssh import SSHHost
        _, refid = enrolled_host
        with app.app_context():
            host_id = SSHHost.query.filter_by(refid=refid).one().id
        assert post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/revoke', {}).status_code == 200
        refusals = self._refusals(app)
        assert host.run('sync').returncode == 0
        assert 'renewal stopped: this host is revoked' in host.run('status').stdout.replace('Renewal stopped', 'renewal stopped')
        assert self._refusals(app) == refusals + 1
        assert host.run('sync').returncode == 0
        assert self._refusals(app) == refusals + 1

    @pytest.mark.parametrize('code', [403, 404])
    def test_a_refusal_that_is_not_ucms_is_retried(self, app, host, enrolled_host, monkeypatch, code):
        from werkzeug.exceptions import Forbidden, NotFound
        from services import ssh_host_service
        _, refid = enrolled_host
        real = ssh_host_service.challenge

        # A proxy in front of UCM: a 403 or 404 without UCM's state stops nothing
        def proxy(host_refid):
            raise (Forbidden if code == 403 else NotFound)()
        monkeypatch.setattr(ssh_host_service, 'challenge', proxy)
        out = host.run('sync')
        assert out.returncode == 1 and f'renewal check failed (HTTP {code})' in out.stderr, out.stderr
        assert 'RENEWAL_STOPPED' not in host.conf()
        monkeypatch.setattr(ssh_host_service, 'challenge', real)
        self._age(app, refid)
        out = host.run('sync')
        assert 'host certificate renewed' in out.stderr, out.stderr

    def test_an_unknown_host_stops_asking(self, app, host, enrolled_host):
        from models.ssh import SSHHost
        _, refid = enrolled_host
        with app.app_context():
            db.session.delete(SSHHost.query.filter_by(refid=refid).one())
            db.session.commit()
        assert host.run('sync').returncode == 0
        assert host.conf()['RENEWAL_STOPPED'] == 'unknown host'

    def test_a_disabled_renewal_waits_and_resumes(self, app, auth_client, host, enrolled_host):
        from models.ssh import SSHHost
        _, refid = enrolled_host
        with app.app_context():
            host_id = SSHHost.query.filter_by(refid=refid).one().id
        post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/auto-renew', {'enabled': False})
        self._age(app, refid)
        assert host.run('sync').returncode == 0
        assert 'RENEWAL_STOPPED' not in host.conf()
        post_json(auth_client, f'/api/v2/ssh/hosts/{host_id}/auto-renew', {'enabled': True})
        out = host.run('sync')
        assert 'host certificate renewed' in out.stderr, out.stderr

    def test_the_krl_pull_names_the_host(self, app, auth_client, host, server, enrolled_host):
        from models.ssh import SSHHost
        _, refid = enrolled_host
        user_ca = _create_ssh_ca(auth_client, descr=f'Agent named pull CA {host.root.parent.name}')
        assert host.install(_installer(server, user_ca['refid'])).returncode == 0
        with app.app_context():
            assert SSHHost.query.filter_by(refid=refid).one().last_krl_sync_at is not None
