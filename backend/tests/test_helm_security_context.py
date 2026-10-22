"""The Helm chart runs UCM as the image's non-root user, with a restricted context."""
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHART = ROOT / 'charts' / 'ucm'


def _image_uid():
    match = re.search(r'useradd\b[^\n]*-u (\d+)[^\n]*\bucm\b', (ROOT / 'Dockerfile').read_text())
    return int(match.group(1))


def _check(pod, container):
    uid = _image_uid()
    assert pod['runAsNonRoot'] is True
    assert pod['runAsUser'] == uid and pod['runAsGroup'] == uid and pod['fsGroup'] == uid
    assert pod['seccompProfile'] == {'type': 'RuntimeDefault'}
    assert container['allowPrivilegeEscalation'] is False
    assert container['capabilities']['drop'] == ['ALL']


def test_default_values_match_the_image_user():
    values = yaml.safe_load((CHART / 'values.yaml').read_text())
    _check(values['podSecurityContext'], values['securityContext'])


@pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')
def test_rendered_deployment_carries_the_context():
    rendered = subprocess.run(['helm', 'template', 't', str(CHART)],
                              capture_output=True, text=True, check=True).stdout
    deploy = next(d for d in yaml.safe_load_all(rendered) if d and d['kind'] == 'Deployment')
    spec = deploy['spec']['template']['spec']
    _check(spec['securityContext'], spec['containers'][0]['securityContext'])
