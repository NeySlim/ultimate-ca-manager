"""The cleartext protocol Ingress (port 8080) carries only its own annotations."""
import pathlib
import shutil
import subprocess

import pytest
import yaml

CHART = pathlib.Path(__file__).resolve().parents[2] / 'charts' / 'ucm'

pytestmark = pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')


def _ingresses(*sets):
    args = ['helm', 'template', 't', str(CHART), '--set', 'ingress.enabled=true',
            '--set', 'ingress.protocolHttp.enabled=true',
            '--set-string', 'ingress.annotations.nginx\\.ingress\\.kubernetes\\.io/backend-protocol=HTTPS']
    for s in sets:
        args += ['--set-string', s]
    out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    return {d['metadata']['name']: d for d in yaml.safe_load_all(out) if d and d['kind'] == 'Ingress'}


def test_the_protocol_ingress_never_inherits_the_ui_annotations():
    """backend-protocol HTTPS of the UI would make the controller speak TLS to port 8080."""
    ing = _ingresses()
    assert ing['t-ucm']['metadata']['annotations'] == {
        'nginx.ingress.kubernetes.io/backend-protocol': 'HTTPS'}
    proto = ing['t-ucm-protocol']
    assert 'annotations' not in proto['metadata'], proto['metadata']
    assert proto['spec']['rules'][0]['http']['paths'][0]['backend']['service']['port'] == {'name': 'http'}


def test_the_protocol_ingress_takes_its_own_annotations():
    ing = _ingresses('ingress.protocolHttp.annotations.example\\.org/x=y')
    assert ing['t-ucm-protocol']['metadata']['annotations'] == {'example.org/x': 'y'}
    assert 'example.org/x' not in ing['t-ucm']['metadata']['annotations']
