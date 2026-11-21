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


def test_nodes_share_a_required_database_key_neg():
    """Integration secrets: without one key for both nodes, each derives its own."""
    assert '${UCM_DB_ENCRYPTION_KEY:?' in TEXT
    assert not re.search(r'\$\{UCM_DB_ENCRYPTION_KEY:?-', TEXT)
    a, b = (DOC['services'][n]['environment'] for n in ('ucm-1', 'ucm-2'))
    assert a['UCM_DB_ENCRYPTION_KEY'] == b['UCM_DB_ENCRYPTION_KEY']


def test_load_balancer_certificate_readability_is_stated_and_checked_pos():
    header = TEXT.split('name: ucm-ha')[0]
    assert 'HA_LB_CERT' in header and 'uid 99' in header and '--wait' in header
    check = DOC['services']['lb']['healthcheck']['test']
    assert 'haproxy' in ' '.join(check) and '-c' in check


def test_password_file_comment_does_not_name_a_fixed_node_neg():
    assert 'exec ucm-1 cat' not in TEXT
    assert 'Initial administrator' in TEXT  # the log line that names the node holding it


def test_load_balancer_retries_a_request_on_the_other_node_pos():
    cfg = DOC['configs']['haproxy_cfg']['content']
    assert re.search(r'^\s*option redispatch\b', cfg, re.M)
    assert re.search(r'^\s*retries [1-9]', cfg, re.M)


def test_a_stopping_node_gets_the_time_of_a_clean_stop_pos():
    """Docker's default 10 s would kill a node whose scheduled task takes its 30 s grace before
    its row is released (docs/HA.md, Upgrading)."""
    for name in ('ucm-1', 'ucm-2'):
        grace = DOC['services'][name]['stop_grace_period']
        assert grace.endswith('s') and int(grace[:-1]) >= 45
