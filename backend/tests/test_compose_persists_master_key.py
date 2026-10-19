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
