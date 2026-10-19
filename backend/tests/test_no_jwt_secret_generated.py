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


def _heredoc_keys(path, marker='ENVEOF'):
    """Variables of the env file a packaging script writes (its here-document)."""
    text = (ROOT / path).read_text()
    keys = set()
    for body in re.findall(rf"<<\s*'?{marker}'?\n(.*?)\n{marker}", text, re.S):
        keys |= {m.group(1) for m in re.finditer(r'^#?\s*([A-Z][A-Z0-9_]+)=', body, re.M)}
    return keys


@pytest.mark.parametrize('path', ['packaging/debian/postinst', 'packaging/rpm/ucm.spec'])
def test_packages_write_no_jwt_variable(path):
    keys = _heredoc_keys(path)
    assert 'SECRET_KEY' in keys
    assert not {k for k in keys if k.startswith('JWT_')}


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
