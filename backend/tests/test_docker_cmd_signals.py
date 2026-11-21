"""The image's default command leaves gunicorn as PID 1 (the entrypoint ends in exec "$@"),
so `docker stop` reaches its SIGTERM handler and a clean stop releases the node's row."""
import json
import os
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND_DIR = '/opt/ucm/backend'


def _cmd():
    dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
    return json.loads(re.findall(r'^CMD (\[.*\])\s*$', dockerfile, re.M)[-1])


def test_the_default_command_runs_gunicorn_in_the_shell_process(tmp_path):
    """A shell that kept gunicorn as its child would ignore SIGTERM as PID 1."""
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    fake = bindir / 'gunicorn'
    fake.write_text('#!/bin/sh\necho "$$ $(pwd)"\n')
    fake.chmod(0o755)
    workdir = tmp_path / 'backend'
    workdir.mkdir()
    argv = [arg.replace(BACKEND_DIR, str(workdir)) for arg in _cmd()]
    env = dict(os.environ, PATH=f'{bindir}:/usr/bin:/bin')
    proc = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, text=True)
    out = proc.communicate(timeout=10)[0].split()
    assert proc.returncode == 0
    assert out == [str(proc.pid), str(workdir)], (argv, out)
