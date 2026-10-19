"""The Docker examples only offer variables something reads.

`.env.docker.example` offered bind-mount directories, PostgreSQL credentials
and resource limits no compose file used, and the dev compose set SQL_DEBUG,
which nothing read. Every variable it offers must be one a compose file uses.
"""
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _compose_variables():
    found = set()
    for path in ROOT.glob('docker-compose*.yml'):
        found |= set(re.findall(r'\$\{([A-Z_][A-Z0-9_]*)', path.read_text()))
    return found


def test_the_env_example_offers_only_variables_compose_reads():
    offered = set(re.findall(r'^#?\s*([A-Z][A-Z0-9_]+)=', (ROOT / '.env.docker.example').read_text(), re.M))
    assert offered and offered <= _compose_variables(), offered - _compose_variables()


class _ComposeLoader(yaml.SafeLoader):
    """Compose tags such as !override hold ordinary values."""


_ComposeLoader.add_multi_constructor('!', lambda loader, suffix, node: (
    loader.construct_sequence(node) if isinstance(node, yaml.SequenceNode)
    else loader.construct_mapping(node) if isinstance(node, yaml.MappingNode)
    else loader.construct_scalar(node)))


def test_the_dev_compose_sets_no_sql_debug():
    dev = yaml.load((ROOT / 'docker-compose.dev.yml').read_text(), Loader=_ComposeLoader)
    env = [e for svc in dev['services'].values() for e in svc.get('environment', [])]
    assert not [e for e in env if str(e).startswith('SQL_DEBUG')]
