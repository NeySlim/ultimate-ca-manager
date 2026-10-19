"""No install path generates a JWT secret any more: UCM has no JWT code.

The DEB/RPM packages, the native setup script, the Docker entrypoint and the
Helm chart each produced a JWT_SECRET_KEY nothing read.
"""
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


def written_env(path, tmp_path):
    """The env file a packaging script writes, produced by running its here-document
    in a throwaway shell; returns ``{name: value}``, commented examples included."""
    text = (ROOT / path).read_text()
    block = re.search(r'^[ \t]*cat > "\$UCM_CONFIG/ucm\.env" << ?\'?ENVEOF\'?\n.*?\nENVEOF$',
                      text, re.S | re.M).group(0)
    env = {'PATH': '/usr/bin:/bin', 'UCM_CONFIG': str(tmp_path), 'UCM_DATA': '/data',
           'SECRET_KEY': 'generated-secret', 'ADMIN_PASS': 'generated-pass'}
    subprocess.run(['bash', '-c', 'set -e\n' + block], env=env, check=True)
    written = (tmp_path / 'ucm.env').read_text()
    return dict(re.findall(r'^#?\s*([A-Z][A-Z0-9_]+)=(\S*)', written, re.M))


@pytest.mark.parametrize('path', ['packaging/debian/postinst', 'packaging/rpm/ucm.spec'])
def test_packages_write_no_jwt_variable(path, tmp_path):
    written = written_env(path, tmp_path)
    assert written['SECRET_KEY'] == 'generated-secret'
    assert not {k for k in written if k.startswith('JWT_')}


def test_the_docker_entrypoint_exports_no_jwt_secret():
    script = (ROOT / 'docker' / 'entrypoint.sh').read_text()
    exports = re.findall(r'^export ([A-Z_]+)=', script, re.M)
    assert 'SECRET_KEY' in exports and 'JWT_SECRET_KEY' not in exports


@pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')
def test_the_chart_holds_no_jwt_secret():
    rendered = subprocess.run(['helm', 'template', 't', str(ROOT / 'charts' / 'ucm')],
                              capture_output=True, text=True, check=True).stdout
    secret = next(d for d in yaml.safe_load_all(rendered) if d and d['kind'] == 'Secret')
    assert 'UCM_SECRET_KEY' in secret['stringData']
    assert 'UCM_JWT_SECRET' not in secret['stringData']
