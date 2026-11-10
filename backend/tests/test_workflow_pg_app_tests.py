"""Every test gated on UCM_TEST_APP_PG_URL runs in the CI PostgreSQL application step."""
import fnmatch
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
STEP = 'Run the application tests on PostgreSQL'
# Not gated on the variable, but HA code whose PostgreSQL behaviour must be exercised too
ALSO_ON_PG = ('tests/test_discovery_recovery_ha.py',)


def _step_patterns():
    text = (ROOT / '.github' / 'workflows' / 'tests.yml').read_text()
    start = text.index(f'- name: {STEP}')
    ends = [i for i in (text.find('\n      - name:', start + 1), text.find('\n  test-', start)) if i != -1]
    return re.findall(r'(tests/\S+\.py)', text[start:min(ends, default=len(text))])


def test_pg_gated_tests_run_in_the_pg_application_step():
    patterns = _step_patterns()
    assert patterns
    tests = ROOT / 'backend' / 'tests'
    gated = [f'tests/{f.name}' for f in sorted(tests.glob('test_*.py'))
             if f.name != pathlib.Path(__file__).name and 'UCM_TEST_APP_PG_URL' in f.read_text()]
    missing = [f for f in [*gated, *ALSO_ON_PG] if not any(fnmatch.fnmatch(f, p) for p in patterns)]
    assert not missing, missing
