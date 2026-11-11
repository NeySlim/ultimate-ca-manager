"""docker-compose.ha.yml: two nodes, shared secrets required, no usable default secret."""
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEXT = (ROOT / 'docker-compose.ha.yml').read_text()
DOC = yaml.safe_load(TEXT)


def test_two_nodes_with_distinct_ids_pos():
    ids = {DOC['services'][n]['environment']['UCM_NODE_ID'] for n in ('ucm-1', 'ucm-2')}
    assert ids == {'ucm-1', 'ucm-2'}
    for n in ('ucm-1', 'ucm-2'):
        assert DOC['services'][n]['environment']['UCM_HA'] == '1'


def test_secrets_are_required_without_default_neg():
    for var in ('UCM_SECRET_KEY', 'KEY_ENCRYPTION_KEY', 'POSTGRES_PASSWORD', 'HA_LB_CERT'):
        assert '${%s:?' % var in TEXT
        assert not re.search(r'\$\{%s:?-' % var, TEXT)


def test_nodes_share_secrets_and_database_pos():
    a, b = (DOC['services'][n]['environment'] for n in ('ucm-1', 'ucm-2'))
    for key in ('UCM_SECRET_KEY', 'KEY_ENCRYPTION_KEY', 'DATABASE_URL'):
        assert a[key] == b[key]


def test_load_balancer_has_cookie_affinity_and_ready_probe_pos():
    cfg = DOC['configs']['haproxy_cfg']['content']
    assert 'cookie UCM_NODE insert' in cfg and '/health/ready' in cfg


def test_load_balancer_forwards_the_client_address_pos():
    cfg = DOC['configs']['haproxy_cfg']['content']
    assert re.search(r'^\s*option forwardfor\b', cfg, re.M)
