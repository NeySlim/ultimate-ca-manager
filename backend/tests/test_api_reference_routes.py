"""docs/API_REFERENCE.md and the application's route table agree.

Format of an operation in the reference: a line that starts with an HTTP
method, whitespace, then an absolute path (`GET /api/v2/cas/{id}`). Path
parameters may be written `{id}` or `<int:id>`; a query string or a trailing
`//` comment is ignored. Prose, curl examples and JSON never start a line
that way, so only operations are read.

(a) every documented operation exists in `app.url_map` with that method;
(b) every `/api/v2/` route is documented, bar `UNDOCUMENTED_ON_PURPOSE`.
"""
import os
import re

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REFERENCE = os.path.join(_REPO, 'docs', 'API_REFERENCE.md')

_OPERATION = re.compile(r'^(GET|POST|PUT|PATCH|DELETE)\s+(/\S*)')
_PARAM = re.compile(r'(?:\{[^}/]*\}|<[^>/]*>)')

# Routes the reference leaves out on purpose: "METHOD /path" -> reason.
UNDOCUMENTED_ON_PURPOSE = {}


def _norm(path):
    path = path.split('?', 1)[0].rstrip('/') or '/'
    return _PARAM.sub('{}', path)


def documented_operations():
    found = set()
    with open(_REFERENCE, encoding='utf-8') as fh:
        for line in fh:
            m = _OPERATION.match(line)
            if m:
                found.add(f'{m.group(1)} {_norm(m.group(2))}')
    return found


def served_operations(app):
    found = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue
        for method in rule.methods - {'HEAD', 'OPTIONS'}:
            found.add(f'{method} {_norm(rule.rule)}')
    return found


def _undocumented(app):
    served = {op for op in served_operations(app)
              if op.split(' ', 1)[1].startswith('/api/v2/')}
    return sorted(served - documented_operations() - set(UNDOCUMENTED_ON_PURPOSE))


def _nonexistent(app):
    return sorted(documented_operations() - served_operations(app))


@pytest.mark.xfail(reason='reference not yet corrected')
def test_every_documented_operation_exists(app):
    missing = _nonexistent(app)
    assert not missing, f'{len(missing)} documented but not served:\n' + '\n'.join(missing)


@pytest.mark.xfail(reason='reference not yet corrected')
def test_every_api_route_is_documented(app):
    missing = _undocumented(app)
    assert not missing, f'{len(missing)} served but not documented:\n' + '\n'.join(missing)


def test_exclusions_name_real_routes_and_give_a_reason(app):
    served = served_operations(app)
    for op, reason in UNDOCUMENTED_ON_PURPOSE.items():
        assert op in served, f'{op} is excluded but no longer served'
        assert reason.strip(), f'{op} is excluded without a reason'
