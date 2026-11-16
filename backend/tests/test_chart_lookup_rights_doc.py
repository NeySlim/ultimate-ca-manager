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


ACTION = re.compile(r'\{\{-?\s*(.*?)\s*-?\}\}', re.S)


def _ha_only(conditions):
    """Under an if whose condition holds only with ha.enabled (and/or never shield a lookup)."""
    return any(c.startswith(('if .Values.ha.enabled', 'if and $renderData .Values.ha.enabled'))
               for c in conditions)


def _template_lookups(text):
    """[(kind, ha_only)] for each lookup in *text*, from the if blocks around it."""
    found, stack = [], []
    for action in ACTION.findall(text):
        head = action.split()[0] if action.split() else ''
        if head in ('if', 'with', 'range', 'define', 'block'):
            stack.append(action)
        elif head == 'else' and stack:
            stack[-1] = action[len('else'):].strip() or 'else'
        elif head == 'end' and stack:
            stack.pop()
        if head == 'if':
            # A lookup in the condition itself runs before the block is entered
            found += [(kind, _ha_only(stack[:-1])) for kind in LOOKUP.findall(action)]
        elif head != 'end':
            found += [(kind, _ha_only(stack)) for kind in LOOKUP.findall(action)]
    return found


def _looked_up():
    """{kind: True when every render reads it, False when only ha.enabled does}."""
    helpers = (TEMPLATES / '_helpers.tpl').read_text()
    reachable = _define(helpers, 'ucm.clusterReachable')
    kinds = {}
    for path in TEMPLATES.glob('*'):
        text = path.read_text()
        for kind, ha_only in _template_lookups(text):
            kinds[kind] = kinds.get(kind, False) or not ha_only
    # The cluster probe: included only under ha.enabled (test_the_cluster_probe_runs_only_under_ha)
    for kind, _ in _template_lookups(reachable):
        if kind == 'ServiceAccount':
            kinds[kind] = False
    return kinds


def test_a_lookup_in_an_or_argument_reads_on_every_render():
    """Before Go 1.18 (Helm 3.10) and/or evaluate every argument: only an if shields a lookup."""
    shielded = ('{{- if .Values.ha.enabled }}{{- $x = (lookup "v1" "PersistentVolumeClaim" ns n) }}'
                '{{- end }}')
    in_or = '{{- if or (not .Values.ha.enabled) (lookup "v1" "PersistentVolumeClaim" ns n) }}{{- end }}'
    after = '{{- if .Values.ha.enabled }}{{- else }}{{ lookup "v1" "Secret" ns n }}{{- end }}'
    assert _template_lookups(shielded) == [('PersistentVolumeClaim', True)]
    assert _template_lookups(in_or) == [('PersistentVolumeClaim', False)]
    assert _template_lookups(after) == [('Secret', False)]


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


RIGHTS_LEADS = (r'[Oo]n every render, ', r'[Ww]ith `ha\.enabled`, also ')


def _stray_rights(text):
    """Resource names the docs cite outside the two sentences the tests above check."""
    spans = [m.span() for lead in RIGHTS_LEADS
             for m in re.finditer(lead + r'`get` on (.+?) in the release namespace', text)]
    names = '|'.join(PLURALS.values())
    return [m.group(0) for m in re.finditer(rf'`({names})`', text)
            if not any(a <= m.start() < b for a, b in spans)]


def test_no_other_sentence_cites_lookup_rights():
    for doc in DOCS:
        assert _stray_rights(doc.read_text()) == [], doc.name
    stale = 'The account needs `get` on `persistentvolumeclaims` only with `ha.enabled`.'
    assert _stray_rights(stale) == ['`persistentvolumeclaims`']
