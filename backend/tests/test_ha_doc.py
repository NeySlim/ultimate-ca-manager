"""docs/HA.md: the single-node to HA procedure must move the data off SQLite first."""
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _single_node_section():
    text = (ROOT / 'docs' / 'HA.md').read_text()
    return re.search(r'### From a single node\n(.*?)(?=\n##)', text, re.S).group(1)


def test_single_node_procedure_migrates_sqlite_before_ha_pos():
    # The chart defaults to SQLite and data migration is refused once in HA.
    assert yaml.safe_load((ROOT / 'charts/ucm/values.yaml').read_text())['database']['type'] == 'sqlite'
    steps = _single_node_section()
    migrate = steps.find('Migrate data and switch')
    pg_upgrade = steps.find('database.type=postgresql')
    ha_upgrade = steps.find('ha.enabled=true`, then check')
    assert -1 < migrate < pg_upgrade < ha_upgrade


def _section(title):
    text = (ROOT / 'docs' / 'HA.md').read_text()
    return re.search(r'### %s\n(.*?)(?=\n##)' % re.escape(title), text, re.S).group(1)


def test_no_polling_fallback_claimed_neg():
    # The UI client opens a WebSocket only, so no document may justify affinity by a polling fallback.
    for rel in ('docs/HA.md', 'charts/ucm/templates/NOTES.txt', 'charts/ucm/values.yaml', 'docker-compose.ha.yml'):
        assert 'polling' not in (ROOT / rel).read_text().lower(), rel


def test_socket_io_bullet_states_websocket_only_pos():
    bullet = next(l for l in _section('Session affinity').splitlines() if l.startswith('- **Socket.IO'))
    assert 'WebSocket' in bullet and 'upgrade' in bullet and 'Invalid session' not in bullet


def test_rate_limit_figures_use_the_code_defaults_pos():
    # flask-limiter defaults (200/min) and 5/min password sign-in are the lower limits across N nodes.
    text = _section('Rate limits')
    assert '200 × N' in text and '5 × N' in text and '2000' in text
    assert '600 × N' not in text and '30 × N' not in text


def test_clock_bullet_names_the_leases_on_the_node_clock_pos():
    # The ACME order lease and the scheduled backup reservation compare utc_now() of the node.
    bullet = next(l for l in (ROOT / 'docs' / 'HA.md').read_text().splitlines()
                  if l.startswith('- **Synchronised clocks'))
    assert 'Heartbeats, leases and the staleness test' not in bullet
    assert 'ACME order lease' in bullet and 'scheduled backup' in bullet

