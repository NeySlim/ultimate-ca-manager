"""The rights the docs ask for match every resource the chart's lookups read, and when."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / 'charts' / 'ucm' / 'templates'
DOCS = (ROOT / 'docs' / 'HA.md', ROOT / 'charts' / 'ucm' / 'README.md')
PLURALS = {'ServiceAccount': 'serviceaccounts', 'Secret': 'secrets',
           'PersistentVolumeClaim': 'persistentvolumeclaims'}
# Any API group: "v1", "apps/v1", "networking.k8s.io/v1"
LOOKUP = re.compile(r'lookup\s+"[\w.-]+(?:/[\w.-]+)?"\s+"(\w+)"')


def _define(text, name):
    start = text.index(f'{{{{- define "{name}" -}}}}')
    nxt = re.search(r'\{\{-? define ', text[start + 1:])
    return text[start:start + 1 + nxt.start()] if nxt else text[start:]


def _looked_up():
    """{kind: True when every render reads it, False when only ha.enabled does}."""
    helpers = (TEMPLATES / '_helpers.tpl').read_text()
    reachable = _define(helpers, 'ucm.clusterReachable')
    kinds = {}
    for path in TEMPLATES.glob('*'):
        for line in path.read_text().splitlines():
            for kind in LOOKUP.findall(line):
                # Read only under ha.enabled: the cluster probe, and the data claim kept in HA
                ha_only = (line in reachable and kind == 'ServiceAccount'
                           or '(not .Values.ha.enabled) (lookup' in line)
                kinds[kind] = kinds.get(kind, False) or not ha_only
    return kinds


def _rights(text, lead):
    found = re.findall(lead + r'`get` on (.+?) in the release namespace', text)
    assert found, f'no sentence on the lookup rights ({lead})'
    return [set(re.findall(r'`([a-z]+)`', f)) for f in found]


def test_the_lookup_pattern_sees_every_api_group():
    assert LOOKUP.findall('lookup "v1" "Secret" ns n') == ['Secret']
    assert LOOKUP.findall('(lookup "apps/v1" "Deployment" ns n)') == ['Deployment']
    assert LOOKUP.findall('lookup "networking.k8s.io/v1" "Ingress" ns n') == ['Ingress']


def test_every_looked_up_kind_is_known():
    assert _looked_up() and set(_looked_up()) <= set(PLURALS)


def test_the_cluster_probe_runs_only_under_ha():
    helpers = (TEMPLATES / '_helpers.tpl').read_text()
    users = [p for p in TEMPLATES.glob('*') if 'include "ucm.clusterReachable"' in p.read_text()]
    assert users == [TEMPLATES / '_helpers.tpl']
    assert 'include "ucm.clusterReachable"' in _define(helpers, 'ucm.haValidate')
    assert '{{- if .Values.ha.enabled -}}' in _define(helpers, 'ucm.haValidate')


def test_the_docs_ask_get_on_what_every_render_reads():
    always = {PLURALS[k] for k, every in _looked_up().items() if every}
    assert 'secrets' in always
    for doc in DOCS:
        for rights in _rights(doc.read_text(), r'[Oo]n every render, '):
            assert rights == always, doc.name


def test_the_docs_ask_get_on_what_ha_reads_on_top():
    ha = {PLURALS[k] for k, every in _looked_up().items() if not every}
    assert ha == {'serviceaccounts', 'persistentvolumeclaims'}
    for doc in DOCS:
        for rights in _rights(doc.read_text(), r'[Ww]ith `ha\.enabled`, also '):
            assert rights == ha, doc.name


def test_a_new_namespace_waits_for_its_default_service_account():
    text = (ROOT / 'docs' / 'HA.md').read_text()
    assert 'kubectl create namespace <name>' in text
    assert 'kubectl get sa default -n <name>' in text
