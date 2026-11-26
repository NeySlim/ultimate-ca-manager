"""The SSH agent of issue #451 against a real sshd: after a sync, sshd refuses a revoked user
certificate it accepted before. sshd runs unprivileged on 127.0.0.1 under a prefix, so the test
needs sshd and curl, which the CI image lacks; it runs in a throwaway container that adds them
(UCM_TEST_SSHD=1)."""
import getpass
import os
import shutil
import socket
import subprocess
import time

import pytest

from tests.ssh_agent_support import AgentHost, live_server
from tests.test_ssh import _create_ssh_ca, post_json
from tests.ssh_cleanup import ssh_rows_stay_in_their_module  # noqa: F401

SSHD = shutil.which('sshd') or ('/usr/sbin/sshd' if os.path.exists('/usr/sbin/sshd') else None)
pytestmark = pytest.mark.skipif(
    not (os.getenv('UCM_TEST_SSHD') and SSHD and shutil.which('curl') and shutil.which('ssh')),
    reason='needs UCM_TEST_SSHD=1, sshd, ssh and curl')


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class RealSshd:
    def __init__(self, host, tmp_path, extra=''):
        self.port = _free_port()
        self.pidfile = tmp_path / 'real-sshd.pid'
        self.log = tmp_path / 'sshd.log'
        self.config = host.ssh / 'sshd_config'
        self.config.write_text(
            f"Port {self.port}\nListenAddress 127.0.0.1\nHostKey {host.ssh / 'ssh_host_ed25519_key'}\n"
            f"PidFile {self.pidfile}\nAuthorizedKeysFile none\nPasswordAuthentication no\n"
            f"KbdInteractiveAuthentication no\nUsePAM no\nStrictModes no\nLogLevel VERBOSE\n{extra}")
        self.config.chmod(0o600)

    def start(self):
        subprocess.run([SSHD, '-f', str(self.config), '-E', str(self.log)], check=True, timeout=30)
        for _ in range(100):
            if self.pidfile.exists() and self.pidfile.read_text().strip():
                return
            time.sleep(0.1)
        raise AssertionError('sshd did not start: ' + self.log.read_text())

    def listening(self):
        return self.log.read_text().count('Server listening on') if self.log.exists() else 0

    def wait_restart(self, before):
        """sshd re-executes itself on SIGHUP: it answers again once it logs a new listen."""
        for _ in range(100):
            if self.listening() > before:
                return
            time.sleep(0.1)
        raise AssertionError('sshd did not come back after SIGHUP: ' + self.log.read_text())

    def stop(self):
        if self.pidfile.exists():
            subprocess.run(['kill', self.pidfile.read_text().strip()])


def _login(port, key, cert, known_hosts=None, host_alias='127.0.0.1'):
    args = ['ssh', '-F', '/dev/null', '-p', str(port), '-i', str(key), '-o', f'CertificateFile={cert}',
            '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=10']
    if known_hosts:
        args += ['-o', f'UserKnownHostsFile={known_hosts}', '-o', 'StrictHostKeyChecking=yes',
                 '-o', f'HostKeyAlias={host_alias}']
    else:
        args += ['-o', 'UserKnownHostsFile=/dev/null', '-o', 'StrictHostKeyChecking=no']
    return subprocess.run(args + [f'{getpass.getuser()}@127.0.0.1', 'true'], capture_output=True, text=True, timeout=60)


def test_a_revoked_certificate_is_refused_after_the_sync(app, auth_client, tmp_path):
    ca = _create_ssh_ca(auth_client, descr='Real sshd KRL CA')
    key = tmp_path / 'id_ed25519'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    r = post_json(auth_client, '/api/v2/ssh/certificates', {
        'ca_id': ca['id'], 'public_key': (tmp_path / 'id_ed25519.pub').read_text(), 'cert_type': 'user',
        'principals': [getpass.getuser()], 'validity_seconds': 3600})
    assert r.status_code == 201, r.data
    cert = r.get_json()['data']
    cert_file = tmp_path / 'id_ed25519-cert.pub'
    cert_file.write_text(cert['certificate'] + '\n')

    host = AgentHost(tmp_path, real_tools=True, sshd_pidfile=tmp_path / 'real-sshd.pid')
    (host.ssh / 'user_ca.pub').write_text(ca['public_key'] + '\n')
    sshd = RealSshd(host, tmp_path, extra=f"TrustedUserCAKeys {host.ssh / 'user_ca.pub'}\n")
    sshd.start()
    try:
        with live_server(app) as url:
            import urllib.request
            script = urllib.request.urlopen(f"{url}/ssh/setup/{ca['refid']}/agent", timeout=30).read().decode()
            listened = sshd.listening()
            out = host.install(script)
            assert out.returncode == 0, out.stderr
            sshd.wait_restart(listened)
            assert _login(sshd.port, key, cert_file).returncode == 0, sshd.log.read_text()

            assert post_json(auth_client, f"/api/v2/ssh/certificates/{cert['id']}/revoke", {}).status_code == 200
            listened = sshd.listening()
            out = host.run('sync')
            assert out.returncode == 0, out.stderr
            sshd.wait_restart(listened)
            refused = _login(sshd.port, key, cert_file)
            assert refused.returncode == 255
            assert 'revoked' in sshd.log.read_text().lower()
    finally:
        sshd.stop()
        host.close()


def _user_login_material(auth_client, tmp_path, descr):
    ca = _create_ssh_ca(auth_client, descr=descr)
    key = tmp_path / 'id_ed25519'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    r = post_json(auth_client, '/api/v2/ssh/certificates', {
        'ca_id': ca['id'], 'public_key': (tmp_path / 'id_ed25519.pub').read_text(), 'cert_type': 'user',
        'principals': [getpass.getuser()], 'validity_seconds': 3600})
    assert r.status_code == 201, r.data
    cert_file = tmp_path / 'id_ed25519-cert.pub'
    cert_file.write_text(r.get_json()['data']['certificate'] + '\n')
    return ca, key, cert_file


def test_a_client_trusting_the_host_ca_accepts_the_enrolled_server(app, auth_client, tmp_path):
    user_ca, key, cert_file = _user_login_material(auth_client, tmp_path, 'Real sshd login CA')
    host_ca = _create_ssh_ca(auth_client, ca_type='host', descr='Real sshd host CA')
    known_hosts = tmp_path / 'known_hosts'
    known_hosts.write_text(f"@cert-authority web01.example.com {host_ca['public_key']}\n")
    r = post_json(auth_client, '/api/v2/ssh/enrollment-tokens',
                  {'ca_id': host_ca['id'], 'principals': ['web01.example.com']})
    token = r.get_json()['data']['token']

    host = AgentHost(tmp_path, real_tools=True, sshd_pidfile=tmp_path / 'real-sshd.pid')
    (host.ssh / 'user_ca.pub').write_text(user_ca['public_key'] + '\n')
    sshd = RealSshd(host, tmp_path, extra=f"TrustedUserCAKeys {host.ssh / 'user_ca.pub'}\n")
    sshd.start()
    try:
        alias = 'web01.example.com'
        before = _login(sshd.port, key, cert_file, known_hosts, alias)
        assert before.returncode == 255 and 'Host key verification failed' in before.stderr
        with live_server(app) as url:
            import urllib.request
            script = urllib.request.urlopen(f"{url}/ssh/setup/{host_ca['refid']}/agent", timeout=30).read().decode()
            listened = sshd.listening()
            out = host.install(script, env={'UCM_ENROLL_TOKEN': token})
            assert out.returncode == 0, out.stderr
        sshd.wait_restart(listened)
        after = _login(sshd.port, key, cert_file, known_hosts, alias)
        assert after.returncode == 0, after.stderr + sshd.log.read_text()
    finally:
        sshd.stop()
        host.close()
