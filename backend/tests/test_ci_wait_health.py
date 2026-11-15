"""scripts/ci/wait-health.sh: HTTP 200 and a healthy UCM body within a bounded wait, or failure;
and the container steps of the workflows that rely on it."""
import http.server
import json
import os
import shutil
import socket
import subprocess
import threading
import time

import pytest

from tests.workflow_support import ROOT, load, render

SCRIPT = ROOT / 'scripts' / 'ci' / 'wait-health.sh'
HEALTHY = {'status': 'ok', 'service': 'ucm', 'version': '3.0', 'fips_active': False, 'websocket': True}

pytestmark = pytest.mark.skipif(not (shutil.which('curl') and shutil.which('jq')), reason='needs curl and jq')


class _Server:
    """A local HTTP server whose answers follow `plan`: a list of (status, body), the last one repeated."""

    def __init__(self, plan):
        self.plan, self.hits = list(plan), 0
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                status, body = outer.plan[min(outer.hits, len(outer.plan) - 1)]
                outer.hits += 1
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.httpd.server_address[1]}/api/v2/health'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _run(url, timeout='2'):
    t0 = time.monotonic()
    proc = subprocess.run(['bash', str(SCRIPT), url, timeout], capture_output=True, text=True, timeout=60,
                          env={'PATH': os.environ['PATH']})
    return proc, time.monotonic() - t0


@pytest.mark.parametrize('plan, ok', [
    ([(200, HEALTHY)], True),
    ([(503, b'starting'), (503, b'starting'), (200, HEALTHY)], True),
    ([(200, {**HEALTHY, 'safe_mode': True, 'safe_mode_reason': 'encryption_key_missing'})], False),
    ([(200, {**HEALTHY, 'status': 'error'})], False),
    ([(200, {'status': 'ok'})], False),            # not UCM answering
    ([(200, b'<html>ok</html>')], False),
    ([(500, HEALTHY)], False),
])
def test_the_answer_decides(plan, ok):
    server = _Server(plan)
    try:
        proc, elapsed = _run(server.url, '2')
    finally:
        server.close()
    assert (proc.returncode == 0) is ok, proc.stdout + proc.stderr
    if not ok:
        assert 'not healthy within 2s' in proc.stderr and elapsed < 2 + 7
        assert server.hits >= 2  # an unhealthy answer is retried until the deadline


def test_no_answer_fails_within_the_bound():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    proc, elapsed = _run(f'http://127.0.0.1:{port}/api/v2/health', '2')
    assert proc.returncode == 1 and 'last HTTP 000' in proc.stderr
    assert 2 <= elapsed < 2 + 7


@pytest.mark.parametrize('timeout', ['', 'abc', '-1'])
def test_a_bad_timeout_is_refused(timeout):
    proc, _ = _run('http://127.0.0.1:1/', timeout)
    assert proc.returncode == 2


def _stub_run(tmp_path, step_run, probe_rc):
    """Run a workflow step with stand-ins for docker and the probe; returns (rc, probe args, docker calls)."""
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    ci = tmp_path / 'scripts' / 'ci'
    ci.mkdir(parents=True)
    probe_log, docker_log = tmp_path / 'probe', tmp_path / 'docker'
    for path, body in ((ci / 'wait-health.sh', f'printf "%s\\n" "$@" > {probe_log}\nexit {probe_rc}\n'),
                       (bin_dir / 'docker', f'echo "$*" >> {docker_log}\n'
                        'case "$1" in inspect) echo 0;; ps) echo ucm-test ucm-smoke;; esac\n')):
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755)
    proc = subprocess.run(['bash', '-e', '-c', step_run], cwd=tmp_path, capture_output=True, text=True,
                          env={'PATH': f'{bin_dir}:/usr/bin:/bin'}, timeout=30)
    probe = probe_log.read_text().split() if probe_log.exists() else None
    docker = docker_log.read_text().splitlines() if docker_log.exists() else []
    return proc.returncode, probe, docker


def _steps():
    build = load('tests.yml')['jobs']['build-test']['steps']
    yield 'tests.yml:build-test', next(s for s in build if s.get('name') == 'Test Docker image')
    for name in ('smoke-sqlite', 'smoke-postgres'):
        steps = load('release-smoke.yml')['jobs'][name]['steps']
        yield f'release-smoke.yml:{name}', next(s for s in steps if str(s.get('name', '')).startswith('Boot UCM'))


CTX = {'steps': {'ver': {'outputs': {'image': 'example/ucm', 'version': '3.0'}}}}


@pytest.mark.parametrize('where, step', list(_steps()), ids=lambda v: v if isinstance(v, str) else '')
@pytest.mark.parametrize('probe_rc', [0, 1])
def test_the_container_steps_follow_the_probe(tmp_path, where, step, probe_rc):
    assert 'sleep' not in step['run'], where
    rc, probe, docker = _stub_run(tmp_path, render(step['run'], CTX), probe_rc)
    assert probe and probe[0].startswith('https://localhost:8443/') and probe[0].endswith('health'), (where, probe)
    assert int(probe[1]) <= 180, where
    assert (rc == 0) is (probe_rc == 0), (where, rc)
    if probe_rc:
        assert any(c.startswith('logs ') for c in docker), (where, docker)


@pytest.mark.skipif(not shutil.which('shellcheck'), reason='shellcheck not installed')
def test_the_script_passes_shellcheck():
    assert subprocess.run(['shellcheck', str(SCRIPT)]).returncode == 0
