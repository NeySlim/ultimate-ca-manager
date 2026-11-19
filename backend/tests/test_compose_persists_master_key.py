"""Every bundled compose file keeps /etc/ucm (master.key) on a named volume."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
STANDALONE = ['docker-compose.yml', 'docker-compose.simple.yml', 'docker-compose.hsm.yml']


@pytest.mark.parametrize('name', STANDALONE)
def test_etc_ucm_is_a_declared_named_volume(name):
    doc = yaml.safe_load((ROOT / name).read_text())
    ucm = [s for s in doc['services'].values()
           if 'ultimate-ca-manager' in str(s.get('image', ''))]
    assert ucm, f'{name}: no UCM service'
    for service in ucm:
        sources = [v.split(':')[0] for v in service.get('volumes', [])
                   if v.split(':')[1] == '/etc/ucm']
        assert len(sources) == 1, f'{name}: /etc/ucm is not mounted'
        # A named volume, declared at the top level, rather than an anonymous one.
        assert sources[0] in (doc.get('volumes') or {}), f'{name}: {sources[0]} not declared'


DOCS = ['README.md', 'DOCKER_QUICKSTART.md', 'DOCKERHUB_README.md', 'UPGRADE.md',
        'docs/HSM_DOCKER.md', 'docs/installation/README.md', 'docs/installation/docker.md']


def _ucm_docker_runs(text):
    """Every complete `docker run` of the UCM image, continuation lines joined."""
    joined = text.replace('\\\n', ' ')
    return [line for line in joined.splitlines()
            if 'docker run' in line and 'ultimate-ca-manager' in line and '...' not in line]


@pytest.mark.parametrize('name', DOCS)
def test_documented_docker_run_mounts_etc_ucm(name):
    runs = _ucm_docker_runs((ROOT / name).read_text())
    assert runs, f'{name}: no docker run of the UCM image'
    # Without its own volume /etc/ucm is anonymous and no master key is created there
    missing = [r.strip() for r in runs if ':/etc/ucm' not in r]
    assert not missing, f'{name}: /etc/ucm not mounted in {missing}'
