"""The maintenance branch v2.x is a release branch for the CI: suites, FIPS build, RC sanity build, image tags.

Each `if:`, concurrency key and image tag is evaluated on concrete cases by a small evaluator of the
GitHub expression subset the workflows use. It proves what the expressions compute for these contexts;
it does not prove that GitHub fills the contexts this way, nor that a run really starts (only a real run does).
"""
import pathlib
import re

import pytest
import yaml

WORKFLOWS = pathlib.Path(__file__).resolve().parents[2] / '.github' / 'workflows'

_TOKEN = re.compile(r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<op>==|!=|&&|\|\||!|\(|\)|,)"
                    r"|(?P<num>[0-9]+)|(?P<name>[A-Za-z_][\w.-]*))")


def _truthy(v):
    return v not in (False, None, '', 0)


def _eq(a, b):
    # GitHub compares strings case-insensitively
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    return a == b


class _Expr:
    """Recursive descent over ||, &&, ==/!=, !, literals, context names and startsWith/contains."""

    def __init__(self, text, ctx):
        self.toks, pos, text = [], 0, text.strip()
        while pos < len(text):
            m = _TOKEN.match(text, pos)
            if not m or m.end() == pos:
                raise AssertionError(f'cannot parse {text[pos:]!r}')
            pos = m.end()
            self.toks.append((m.lastgroup, m.group(m.lastgroup)))
        self.i, self.ctx = 0, ctx

    def run(self):
        v = self._or()
        assert self.i == len(self.toks), f'trailing tokens {self.toks[self.i:]}'
        return v

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def _take(self, op):
        assert self._peek() == ('op', op), f'expected {op} at {self.toks[self.i:]}'
        self.i += 1

    def _or(self):
        left = self._and()
        while self._peek() == ('op', '||'):
            self.i += 1
            right = self._and()
            left = left if _truthy(left) else right
        return left

    def _and(self):
        left = self._cmp()
        while self._peek() == ('op', '&&'):
            self.i += 1
            right = self._cmp()
            left = right if _truthy(left) else left
        return left

    def _cmp(self):
        left = self._unary()
        if self._peek() in (('op', '=='), ('op', '!=')):
            op = self._peek()[1]
            self.i += 1
            right = self._unary()
            return _eq(left, right) if op == '==' else not _eq(left, right)
        return left

    def _unary(self):
        if self._peek() == ('op', '!'):
            self.i += 1
            return not _truthy(self._unary())
        return self._primary()

    def _primary(self):
        kind, val = self._peek()
        self.i += 1
        if kind == 'str':
            return val[1:-1].replace("''", "'")
        if kind == 'num':
            return int(val)
        if (kind, val) == ('op', '('):
            v = self._or()
            self._take(')')
            return v
        if kind == 'name':
            if val in ('true', 'false', 'null'):
                return {'true': True, 'false': False, 'null': None}[val]
            if self._peek() == ('op', '('):
                self.i += 1
                args = [self._or()]
                while self._peek() == ('op', ','):
                    self.i += 1
                    args.append(self._or())
                self._take(')')
                a, b = (str(x).lower() for x in args)
                return {'startsWith': a.startswith(b), 'contains': b in a}[val]
            if val not in self.ctx:
                raise KeyError(f'no context value for {val}')
            return self.ctx[val]
        raise AssertionError(f'unexpected token {val!r}')


def evaluate(expr, ctx):
    expr = str(expr).strip()
    m = re.fullmatch(r'\$\{\{(.*)\}\}', expr, re.S)
    return _Expr(m.group(1) if m else expr, ctx).run()


def render(text, ctx):
    def one(m):
        v = evaluate(m.group(1), ctx)
        return str(v).lower() if isinstance(v, bool) else str(v)
    return re.sub(r'\$\{\{(.*?)\}\}', one, str(text))


def _load(name):
    return yaml.safe_load((WORKFLOWS / name).read_text())


def _on(data):
    # YAML 1.1 reads the bare key `on` as True
    return data.get('on', data.get(True))


def _branch_matches(pattern, branch):
    rx = ''.join('.*' if part == '**' else '[^/]*' if part == '*' else re.escape(part)
                 for part in re.split(r'(\*\*|\*)', pattern))
    return re.fullmatch(rx, branch) is not None


def _github(event, branch=None, sha='c0ffee'):
    ref = f'refs/heads/{branch}' if event in ('push', 'schedule', 'workflow_dispatch') else 'refs/pull/7/merge'
    name = branch if branch else '7/merge'
    return {'github.event_name': event, 'github.ref': ref, 'github.ref_name': name, 'github.sha': sha,
            'github.workflow': 'Tests & Quality Checks'}


CASES = [('push', 'v2.x'), ('push', 'dev'), ('push', 'test'), ('push', 'main'), ('pull_request', None),
         ('schedule', 'main')]


# ---- 1. tests.yml ------------------------------------------------------------------------------

def test_a_push_to_the_maintenance_branch_triggers_the_suites():
    branches = _on(_load('tests.yml'))['push']['branches']
    assert any(_branch_matches(p, 'v2.x') for p in branches), branches


@pytest.mark.parametrize('event,branch,expected', [
    ('push', 'v2.x', True), ('push', 'test', True), ('push', 'main', True), ('push', 'dev', False),
    ('push', 'feature/x', False), ('pull_request', None, False), ('schedule', 'main', True),
    ('workflow_dispatch', 'dev', True),
])
def test_the_sequential_suite_runs_on_release_branches(event, branch, expected):
    job = _load('tests.yml')['jobs']['test-backend-sequential']
    assert _truthy(evaluate(job['if'], _github(event, branch))) is expected


@pytest.mark.parametrize('event,branch,expected', [
    ('push', 'v2.x', True), ('push', 'dev', True), ('push', 'test', False), ('push', 'main', False),
    ('pull_request', None, False), ('schedule', 'main', False), ('workflow_dispatch', 'v2.x', False),
])
def test_the_fips_build_runs_on_dev_and_the_maintenance_branch(event, branch, expected):
    job = _load('tests.yml')['jobs']['build-test-fips']
    assert _truthy(evaluate(job['if'], _github(event, branch))) is expected


@pytest.mark.parametrize('event,branch,per_commit', [
    ('push', 'v2.x', True), ('push', 'test', True), ('push', 'main', True), ('push', 'dev', False),
    ('pull_request', None, False),
])
def test_release_branches_keep_every_run(event, branch, per_commit):
    conc = _load('tests.yml')['concurrency']
    ctx = _github(event, branch, sha='c0ffee')
    group = render(conc['group'], ctx)
    assert group.endswith('-c0ffee') is per_commit, group
    assert _truthy(evaluate(conc['cancel-in-progress'], ctx)) is (not per_commit)


def test_the_nightly_run_is_unchanged():
    data = _load('tests.yml')
    assert _on(data)['schedule'] == [{'cron': '0 3 * * *'}]
    seq = data['jobs']['test-backend-sequential']
    checkout = next(s for s in seq['steps'] if str(s.get('uses', '')).startswith('actions/checkout@'))
    assert render(checkout['with']['ref'], {**_github('schedule', 'main'), 'github.ref': 'refs/heads/main'}) == 'dev'


# ---- 2. test-channel.yml -----------------------------------------------------------------------

@pytest.mark.parametrize('branch,expected', [('v2.x', True), ('test', True), ('dev', False), ('main', False)])
def test_the_rc_sanity_build_runs_on_the_maintenance_branch(branch, expected):
    on = _on(_load('test-channel.yml'))
    assert any(_branch_matches(p, branch) for p in on['push']['branches']) is expected
    assert 'pull_request' not in on


# ---- 4. Docker Hub page ------------------------------------------------------------------------

def _steps(job):
    return _load('build-release.yml')['jobs'][job]['steps']


@pytest.mark.parametrize('latest,expected', [('true', True), ('false', False)])
def test_only_the_latest_image_rewrites_the_docker_hub_page(latest, expected):
    steps = _steps('docker-manifest')
    idx = next(i for i, s in enumerate(steps) if s.get('name') == 'Update Docker Hub description')
    decide = next(i for i, s in enumerate(steps) if s.get('id') == 'latest')
    assert decide < idx
    assert 'if' in steps[idx], 'the Docker Hub page step must be conditional'
    assert _truthy(evaluate(steps[idx]['if'], {'steps.latest.outputs.latest': latest})) is expected


def test_no_other_publishing_job_rewrites_the_docker_hub_page():
    jobs = _load('build-release.yml')['jobs']
    users = [j for j, d in jobs.items() for s in d.get('steps', [])
             if str(s.get('uses', '')).startswith('peter-evans/dockerhub-description@')]
    assert users == ['docker-manifest']


# ---- 5. line tags ------------------------------------------------------------------------------

def _enabled_tags(job, ctx):
    meta = next(s for s in _steps(job) if s.get('id') == 'meta')
    out = set()
    for ln in meta['with']['tags'].splitlines():
        if not ln.strip():
            continue
        fields = dict(f.split('=', 1) for f in render(ln.strip(), ctx).split(','))
        assert fields['type'] == 'raw', ln
        if fields.get('enable', 'true') == 'true':
            out.add(fields['value'])
    return out


@pytest.mark.parametrize('job,suffix', [('docker-manifest', ''), ('docker-fips-manifest', '-fips')])
@pytest.mark.parametrize('latest,line,extra', [
    ('false', '2', {'2'}),            # a maintenance stable after a later major: its line, not latest
    ('true', '2', {'latest', '2'}),   # the highest stable of all
    ('false', '', set()),             # a RC, or an older stable of the line
])
def test_the_image_takes_its_line_tag(job, suffix, latest, line, extra):
    steps = _steps(job)
    ids = [s.get('id') for s in steps]
    assert ids.index('line') < ids.index('meta')
    ctx = {'steps.latest.outputs.latest': latest, 'steps.line.outputs.line': line,
           'needs.build-deb.outputs.version': '2.254.5'}
    expected = {'2.254.5' + suffix} | {('latest' if t == 'latest' else t) + suffix for t in extra}
    assert _enabled_tags(job, ctx) == expected


# ---- 6. release smoke --------------------------------------------------------------------------

def test_the_release_smoke_can_be_run_by_hand_with_a_version():
    """Guard: the documented manual run of a maintenance release needs this entry point."""
    on = _on(_load('release-smoke.yml'))
    assert on['workflow_dispatch']['inputs']['version']['required'] is True
