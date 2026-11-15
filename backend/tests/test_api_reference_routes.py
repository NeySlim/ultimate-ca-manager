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


def test_the_reference_is_read(app):
    assert documented_operations() and served_operations(app)


def test_every_documented_operation_exists(app):
    missing = _nonexistent(app)
    assert not missing, f'{len(missing)} documented but not served:\n' + '\n'.join(missing)


def test_every_api_route_is_documented(app):
    missing = _undocumented(app)
    assert not missing, f'{len(missing)} served but not documented:\n' + '\n'.join(missing)


def test_exclusions_name_real_routes_and_give_a_reason(app):
    served = served_operations(app)
    for op, reason in UNDOCUMENTED_ON_PURPOSE.items():
        assert op in served, f'{op} is excluded but no longer served'
        assert reason.strip(), f'{op} is excluded without a reason'


def test_no_hand_written_endpoint_count():
    # The route table is the count; a number typed into the reference goes stale.
    count = re.compile(r'(?i)(total\s+endpoints|\d+\+?\s+(endpoints|routes|operations)\b)')
    with open(_REFERENCE, encoding='utf-8') as fh:
        stale = [line.strip() for line in fh if count.search(line)]
    assert not stale, 'endpoint count written by hand:\n' + '\n'.join(stale)


_PROTOCOL_SECTION = '## Protocol and Health Endpoints'
_CODE = re.compile(r'`([^`]+)`')


def protocol_paths():
    """Paths of the protocol table; `P` and `Q` followed by `a`, `b` stand for Pa, Pb, Qa, Qb."""
    with open(_REFERENCE, encoding='utf-8') as fh:
        text = fh.read()
    section = text.split(_PROTOCOL_SECTION, 1)[1].split('\n---', 1)[0]
    found = set()
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if not line.startswith('|') or len(cells) < 3 or cells[0] in ('Protocol', '') \
                or set(cells[0]) <= {'-'}:
            continue
        head, _, tail = cells[1].partition('followed by')
        prefixes = [p for p in _CODE.findall(head) if p.startswith('/')]
        if tail:
            found |= {p + s for p in prefixes for s in _CODE.findall(tail)}
        else:
            found |= set(prefixes)
    return {_norm(p) for p in found}


def _served_paths(app):
    return {_norm(r.rule) for r in app.url_map.iter_rules()}


def test_protocol_table_is_read():
    paths = protocol_paths()
    assert '/acme/directory' in paths and '/acme/proxy/{}/directory' in paths


def test_every_cited_protocol_path_exists(app):
    missing = sorted(protocol_paths() - _served_paths(app))
    assert not missing, 'cited but not served:\n' + '\n'.join(missing)


def test_every_acme_route_is_cited(app):
    acme = {p for p in _served_paths(app) if p.startswith('/acme/')}
    missing = sorted(acme - protocol_paths())
    assert not missing, 'served but not cited:\n' + '\n'.join(missing)
