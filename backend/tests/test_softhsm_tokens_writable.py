"""SoftHSM tokens survive where the service runs.

DEB and RPM units run under ProtectSystem=strict, so the token directory must be
opened to the service or every key generation fails on a read-only file system.
The Docker image must keep its tokens in a volume, or a recreated container (an
upgrade) starts from an empty token.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
UNITS = ('packaging/debian/ucm.service', 'packaging/rpm/ucm.service')


def _service_section(unit):
    body = (ROOT / unit).read_text(encoding='utf-8')
    return body.split('[Service]', 1)[1].split('\n[', 1)[0]


@pytest.mark.parametrize('unit', UNITS)
def test_each_unit_opens_the_softhsm_token_directory(unit):
    service = _service_section(unit)
    assert re.search(r'^ReadWritePaths=(.*\s)?-/var/lib/softhsm/tokens(\s|$)', service, re.M), unit


@pytest.mark.parametrize('unit', UNITS)
def test_the_units_stay_strict(unit):
    """Opening one directory is the point, not dropping the sandbox."""
    assert re.search(r'^ProtectSystem=strict\s*$', _service_section(unit), re.M), unit


def test_the_image_keeps_tokens_in_a_volume():
    dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
    tokendir = re.search(r'directories\.tokendir = (\S+?)/?#', dockerfile)
    assert tokendir, 'the Dockerfile no longer sets the SoftHSM token directory'
    volumes = re.findall(r'"([^"]+)"', re.search(r'^VOLUME \[(.*)\]', dockerfile, re.M).group(1))
    assert any(tokendir.group(1).startswith(v.rstrip('/') + '/') for v in volumes), (tokendir.group(1), volumes)


def test_the_entrypoint_creates_the_token_directory_in_the_volume():
    entrypoint = (ROOT / 'docker/entrypoint.sh').read_text(encoding='utf-8')
    assert re.search(r'^DATA_PATH="/opt/ucm/data"$', entrypoint, re.M)
    assert re.search(r'^mkdir -p "\$DATA_PATH"/softhsm/tokens\b', entrypoint, re.M)
