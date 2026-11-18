"""A release run refuses a tag whose commit carries another version in VERSION."""
from tests.workflow_support import evaluate, github_context, load

TAG = github_context('push', 'refs/tags/v3.0-rc3')
BRANCH = github_context('workflow_dispatch', 'refs/heads/feature/x')
TAG_DISPATCH = github_context('workflow_dispatch', 'refs/tags/v3.0-rc3')


def _jobs():
    return load('build-release.yml')['jobs']


def _needs(job):
    needs = job.get('needs', [])
    return needs if isinstance(needs, list) else [needs]


def _closure(jobs, name):
    seen, todo = set(), list(_needs(jobs[name]))
    while todo:
        n = todo.pop()
        if n not in seen:
            seen.add(n)
            todo += _needs(jobs[n])
    return seen


def _steps():
    return _jobs()['validate-tag']['steps']


def _check_index():
    found = [i for i, s in enumerate(_steps()) if 'release_version.py matches' in str(s.get('run', ''))]
    assert len(found) == 1, found
    return found[0]


def _index(pred):
    found = [i for i, s in enumerate(_steps()) if pred(s)]
    assert len(found) == 1, found
    return found[0]


def test_the_step_follows_the_checkout_and_the_grammar_and_names_both_files():
    steps, i = _steps(), _check_index()
    assert i > _index(lambda s: str(s.get('uses', '')).startswith('actions/checkout'))
    assert i > _index(lambda s: 'release_version.py validate' in str(s.get('run', '')))
    run = steps[i]['run']
    assert '"${GITHUB_REF#refs/tags/v}"' in run and 'VERSION' in run


def test_the_step_runs_on_a_tag_and_not_on_a_branch_rehearsal():
    cond = _steps()[_check_index()]['if']
    assert evaluate(cond, {'github': TAG, 'inputs': {}})
    assert evaluate(cond, {'github': TAG_DISPATCH, 'inputs': {'dry_run': False, 'version': '3.0-rc3'}})
    assert not evaluate(cond, {'github': BRANCH, 'inputs': {'dry_run': True, 'version': '3.0-rc3'}})
    assert not evaluate(cond, {'github': TAG_DISPATCH, 'inputs': {'dry_run': True, 'version': '9.9'}})


def test_every_job_waits_for_the_validation():
    jobs = _jobs()
    for name in jobs:
        if name != 'validate-tag':
            assert 'validate-tag' in _closure(jobs, name), name
