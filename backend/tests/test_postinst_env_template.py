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
    # SCEP lives in the database (Protocols > SCEP); SCEP_* in ucm.env are never read.
    assert not {k for k in _template_keys() if k.startswith('SCEP_')}
