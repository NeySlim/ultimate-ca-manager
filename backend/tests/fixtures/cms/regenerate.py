"""Rewrite the CMS golden fixtures from the code as it stands: `python tests/fixtures/cms/regenerate.py`
from backend/ (add --new-keys to remake the keys and certificates first)."""
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))
# Never let an import reach the installed database
_tmp = tempfile.mkdtemp(prefix='ucm-cms-golden-')
os.environ.update(DATA_DIR=_tmp, DATABASE_PATH=os.path.join(_tmp, 'ucm.db'), DATABASE_URL='',
                  UCM_ENV='test')

from tests import cms_golden  # noqa: E402

if '--new-keys' in sys.argv:
    cms_golden._write_material()
for name in cms_golden.CASES:
    (cms_golden.FIXTURES / f'{name}.der').write_bytes(cms_golden.build(name))
errors = {name: cms_golden.build_error(name) for name in cms_golden.ERROR_CASES}
(cms_golden.FIXTURES / 'errors.json').write_text(json.dumps(errors, indent=2, sort_keys=True) + '\n')
print(f'{len(cms_golden.CASES)} fixtures, {len(errors)} refusals')
