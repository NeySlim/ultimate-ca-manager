"""The frontend job runs what the local validation runs: tests, lint and the locale sync check."""
import json
import subprocess

from tests.workflow_support import ROOT, load

EXPECTED = (['test', '--', '--run'], ['run', 'lint'], ['run', 'check:i18n'])


def test_the_frontend_job_runs_tests_lint_and_the_i18n_check(tmp_path):
    scripts = json.loads((ROOT / 'frontend' / 'package.json').read_text())['scripts']
    assert {'test', 'lint', 'check:i18n'} <= set(scripts)
    steps = load('tests.yml')['jobs']['test-frontend']['steps']
    (tmp_path / 'frontend').mkdir()
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    log = tmp_path / 'npm'
    npm = bin_dir / 'npm'
    npm.write_text(f'#!/bin/sh\necho "$(basename "$PWD") $*" >> {log}\n')
    npm.chmod(0o755)
    for step in steps:
        if 'run' in step:
            proc = subprocess.run(['bash', '-e', '-c', step['run']], cwd=tmp_path, capture_output=True, text=True,
                                  env={'PATH': f'{bin_dir}:/usr/bin:/bin'})
            assert proc.returncode == 0, (step.get('name'), proc.stderr)
    calls = [line.split() for line in log.read_text().splitlines()]
    for args in EXPECTED:
        assert ['frontend', *args] in calls, (args, calls)
