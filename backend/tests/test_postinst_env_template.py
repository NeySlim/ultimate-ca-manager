"""The ucm.env written by the DEB postinst only offers variables UCM still reads."""
import re
from pathlib import Path

POSTINST = Path(__file__).resolve().parents[2] / 'packaging' / 'debian' / 'postinst'


def _template_keys():
    text = POSTINST.read_text()
    body = re.search(r"<<\s*'?ENVEOF'?\n(.*?)\nENVEOF", text, re.S).group(1)
    return {m.group(1) for m in re.finditer(r'^#?\s*([A-Z][A-Z0-9_]+)=', body, re.M)}


def test_template_is_found():
    assert 'INITIAL_ADMIN_PASSWORD' in _template_keys()


def test_no_dead_scep_variables():
    # SCEP lives in the database (Protocols > SCEP); SCEP_* in ucm.env have no effect.
    assert not {k for k in _template_keys() if k.startswith('SCEP_')}


SPEC = POSTINST.parents[1] / 'rpm' / 'ucm.spec'


def test_neither_package_writes_an_initial_password():
    """Unset, the first start generates one; a value written here would outlive the first start."""
    for path in (POSTINST, SPEC):
        text = path.read_text()
        assert not re.search(r'^\s*INITIAL_ADMIN_PASSWORD(_FILE)?=', text, re.M), path.name
        assert 'changeme123' not in text, path.name


def test_no_default_password_ships():
    """Allowed: the policy's blocklist, the cleanup of the line older packages wrote, a test seed."""
    root = POSTINST.parents[2]
    allowed = {root / 'backend' / 'security' / 'password_policy.py',
               root / 'packaging' / 'scripts' / 'native-setup.sh',
               root / 'backend' / 'scripts' / 'seed_rc_test.py'}
    found = []
    for top in ('backend', 'packaging', 'docker', 'charts', 'frontend/src'):
        for path in (root / top).rglob('*'):
            if (not path.is_file() or path in allowed or 'tests' in path.parts
                    or '__tests__' in path.parts or 'node_modules' in path.parts
                    or path.suffix in ('.pyc', '.png', '.ico', '.woff2')):
                continue
            if 'changeme123' in path.read_text(errors='ignore'):
                found.append(str(path.relative_to(root)))
    assert not found, found
