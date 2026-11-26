"""The defaults the Docker installation guide gives are those the image's entrypoint sets."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_every_documented_literal_default_is_the_entrypoints():
    entry = (ROOT / 'docker' / 'entrypoint.sh').read_text()
    defaults = dict(re.findall(r'^: "\$\{(\w+):="?([^"}]*)"?\}"', entry, re.M))
    doc = (ROOT / 'docs' / 'installation' / 'docker.md').read_text()
    rows = re.findall(r'^\| `(\w+)` \| `([^`|]*)` \|', doc, re.M)
    checked = {name: value for name, value in rows if name in defaults}
    assert 'UCM_FQDN' in checked and len(checked) >= 5, checked
    assert {n: defaults[n] for n in checked} == checked
