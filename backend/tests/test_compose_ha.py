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


def test_nodes_do_not_autocreate_a_local_softhsm_token_neg():
    for n in ('ucm-1', 'ucm-2'):
        assert DOC['services'][n]['environment']['HSM_AUTO_INIT'] == 'false'


def _resolve(value, env=None):
    """Compose ${VAR:-default} interpolation, nested, with ``env`` (empty by default)."""
    env = env or {}
    pattern = re.compile(r'\$\{(\w+):-((?:[^${}]|\$\{[^{}]*\})*)\}')
    while (m := pattern.search(value)):
        value = value[:m.start()] + env.get(m.group(1), m.group(2)) + value[m.end():]
    return value


def test_nodes_trust_the_fixed_subnet_the_load_balancer_sits_on_pos():
    subnets = [c['subnet'] for c in DOC['networks']['default']['ipam']['config']]
    trusted = DOC['services']['ucm-1']['environment']['UCM_TRUSTED_PROXIES']
    for env in ({}, {'UCM_HA_SUBNET': '10.99.0.0/24'}):
        assert [_resolve(s, env) for s in subnets] == [_resolve(trusted, env)]
    assert _resolve(trusted, {'UCM_TRUSTED_PROXIES': '10.1.2.3'}) == '10.1.2.3'
