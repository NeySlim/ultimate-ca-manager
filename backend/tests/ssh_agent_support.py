"""Running the SSH agent of issue #451 in a test: a live UCM on 127.0.0.1, the agent under a
prefix (UCM_AGENT_ROOT) as an ordinary user, and stand-ins for curl and sshd when the host has
none (the CI image has neither)."""
import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from contextlib import contextmanager

# curl as the agent calls it: -sS --max-time N -o OUT -w '%{http_code}' [-H h] [-X POST --data-binary @f] URL
FAKE_CURL = textwrap.dedent('''\
    #!PYTHON
    import sys, urllib.request, urllib.error
    args, out, fmt, headers, data, method, url = sys.argv[1:], None, None, {}, None, None, None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ('-o', '-w', '-H', '-X', '--data-binary', '--max-time', '--cacert'):
            v = args[i + 1]
            if a == '-o': out = v
            elif a == '-w': fmt = v
            elif a == '-H':
                k, _, val = v.partition(':'); headers[k.strip()] = val.strip()
            elif a == '-X': method = v
            elif a == '--data-binary': data = open(v[1:], 'rb').read() if v.startswith('@') else v.encode()
            i += 2
            continue
        if not a.startswith('-'): url = a
        i += 1
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=60); code, body = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        code, body = e.code, e.read()
    except Exception:
        sys.stdout.write('000'); sys.exit(7)
    if out: open(out, 'wb').write(body)
    if fmt: sys.stdout.write(str(code))
''').replace('PYTHON', sys.executable)

# sshd -t succeeds unless FAKE_SSHD_FAIL names an existing file; -T prints the first RevokedKeys
FAKE_SSHD = textwrap.dedent('''\
    #!/bin/sh
    cfg=""
    mode=""
    while [ $# -gt 0 ]; do
        case "$1" in -t) mode=t ;; -T) mode=T ;; -f) cfg=$2; shift ;; esac
        shift
    done
    echo "sshd -$mode" >> "${FAKE_SSHD_LOG:-/dev/null}"
    if [ -n "${FAKE_SSHD_FAIL:-}" ] && [ -f "$FAKE_SSHD_FAIL" ]; then exit 1; fi
    if [ "$mode" = T ]; then
        for f in "$cfg" $(dirname "$cfg")/sshd_config.d/*.conf; do [ -f "$f" ] && cat "$f"; done \\
          | awk 'tolower($1) == "revokedkeys" && !seen { print "revokedkeys " $2; seen = 1 }
                 tolower($1) == "hostcertificate" { print "hostcertificate " $2 }'
    fi
    exit 0
''')

# A process standing for sshd's master: counts the SIGHUPs it receives
HUP_COUNTER = textwrap.dedent('''\
    import os, signal, sys, time
    path = sys.argv[1]
    open(path, 'w').write('0')
    def hup(*_):
        n = int(open(path).read() or 0) + 1
        open(path, 'w').write(str(n))
    signal.signal(signal.SIGHUP, hup)
    while True:
        time.sleep(1)
''')


@contextmanager
def live_server(app):
    """UCM answering on 127.0.0.1:<port> from a thread; yields its base URL."""
    from werkzeug.serving import make_server
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        thread.join(5)


class AgentHost:
    """A server's file system under *root*, its sshd stood for by FAKE_SSHD and a HUP counter."""

    def __init__(self, tmp_path, real_tools=False, sshd_pidfile=None):
        self.root = tmp_path / 'host'
        self.ssh = self.root / 'etc' / 'ssh'
        self.ssh.mkdir(parents=True)
        self.bin = tmp_path / 'bin'
        self.bin.mkdir()
        self.sshd_log = tmp_path / 'sshd.log'
        if not real_tools:
            for name, body in (('curl', FAKE_CURL), ('sshd', FAKE_SSHD)):
                path = self.bin / name
                path.write_text(body)
                path.chmod(0o755)
        (self.ssh / 'sshd_config').write_text('Port 2222\nMatch User nobody\n    PasswordAuthentication no\n')
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(self.ssh / 'ssh_host_ed25519_key')],
                       check=True, capture_output=True)
        self.hups = tmp_path / 'hups'
        self._counter = None
        if sshd_pidfile:
            self.pidfile = sshd_pidfile
        else:
            self.pidfile = tmp_path / 'sshd.pid'
            self._counter = subprocess.Popen([sys.executable, '-c', HUP_COUNTER, str(self.hups)])
            for _ in range(50):
                if self.hups.exists():
                    break
                time.sleep(0.1)
            self.pidfile.write_text(str(self._counter.pid))
        self.env = {**os.environ, 'PATH': f'{self.bin}:{os.environ["PATH"]}', 'UCM_AGENT_ROOT': str(self.root),
                    'UCM_SSHD_PIDFILE': str(self.pidfile), 'UCM_AGENT_NO_SCHEDULER': '1',
                    'FAKE_SSHD_LOG': str(self.sshd_log)}
        self.env.pop('PYTHONPATH', None)

    @property
    def conf_dir(self):
        return self.ssh / 'ucm'

    @property
    def krl(self):
        return self.conf_dir / 'revoked_keys'

    @property
    def agent(self):
        return self.root / 'usr' / 'local' / 'sbin' / 'ucm-ssh-agent'

    def hup_count(self):
        return int(self.hups.read_text() or 0)

    def conf(self):
        text = (self.conf_dir / 'agent.conf').read_text() if (self.conf_dir / 'agent.conf').exists() else ''
        return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)

    def install(self, script, *args, env=None):
        return subprocess.run(['sh', '-s', '--', *args], input=script, text=True, capture_output=True,
                              env={**self.env, **(env or {})}, timeout=120)

    def run(self, *args, env=None):
        return subprocess.run(['sh', str(self.agent), *args], text=True, capture_output=True,
                              env={**self.env, **(env or {})}, timeout=120)

    def close(self):
        if self._counter:
            self._counter.send_signal(signal.SIGTERM)
            self._counter.wait(5)
