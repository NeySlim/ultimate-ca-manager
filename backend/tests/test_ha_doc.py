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


def test_no_polling_fallback_claimed_neg():
    # The UI client opens a WebSocket only, so no document may justify affinity by a polling fallback.
    for rel in ('docs/HA.md', 'charts/ucm/templates/NOTES.txt', 'charts/ucm/values.yaml', 'docker-compose.ha.yml'):
        assert 'polling' not in (ROOT / rel).read_text().lower(), rel


def test_in_page_links_of_ha_doc_resolve_pos():
    text = (ROOT / 'docs' / 'HA.md').read_text()
    anchors = {re.sub(r'[^a-z0-9 -]', '', h.lower()).replace(' ', '-')
               for h in re.findall(r'^#+ (.+)$', text, re.M)}
    assert {a for a in re.findall(r'\]\(#([^)]+)\)', text) if a not in anchors} == set()
