"""The rights the HA docs ask for match every resource the chart's lookups read."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / 'charts' / 'ucm' / 'templates'
PLURALS = {'ServiceAccount': 'serviceaccounts', 'Secret': 'secrets',
           'PersistentVolumeClaim': 'persistentvolumeclaims'}


def _looked_up():
    kinds = set()
    for path in TEMPLATES.glob('*'):
        kinds |= set(re.findall(r'lookup\s+"v1"\s+"(\w+)"', path.read_text()))
    return kinds


def _rights(text):
    # "`get` on `a`, `b` and `c` in the release namespace"
    found = re.findall(r'`get` on (.+?) in the release namespace', text)
    assert found, 'no sentence on the lookup rights'
    return [set(re.findall(r'`([a-z]+)`', f)) for f in found]


def test_every_looked_up_kind_is_known():
    assert _looked_up() and _looked_up() <= set(PLURALS)


def test_the_docs_ask_get_on_every_looked_up_resource():
    wanted = {PLURALS[k] for k in _looked_up()}
    for doc in (ROOT / 'docs' / 'HA.md', ROOT / 'charts' / 'ucm' / 'README.md'):
        for rights in _rights(doc.read_text()):
            assert rights == wanted, doc.name

