"""The workflow expression evaluator the CI structure tests rely on."""
import pytest

from tests.workflow_support import evaluate, github_context, render

CTX = {'github': github_context('push', 'refs/heads/sextant'), 'inputs': {'version': '3.0-rc1'},
       'needs': {'build-deb': {'outputs': {'version': '3.0'}}}}


@pytest.mark.parametrize('expr, value', [
    ("github.event_name == 'push'", True),
    ("github.event_name != 'push'", False),
    ("github.ref_name == 'SEXTANT'", True),  # comparisons ignore case, as on GitHub
    ("!(github.event_name == 'schedule')", True),
    ("github.event_name == 'schedule' && 'dev' || github.ref", 'refs/heads/sextant'),
    ("github.event_name == 'push' && 'dev' || github.ref", 'dev'),
    ("startsWith(github.ref, 'refs/tags/')", False),
    ("contains(github.ref, 'sext')", True),
    ("${{ format('x') }}", ValueError),
    ("${{ inputs.version }}", '3.0-rc1'),
    ("needs.build-deb.outputs.version", '3.0'),
    ("github.event.workflow_run.head_branch", None),
    ("cancelled()", False),
    ("unknown.thing", ValueError),
    ("refs/tags/v${{ inputs.version }}", ValueError),
])
def test_expressions(expr, value):
    if value is ValueError:
        with pytest.raises(ValueError):
            evaluate(expr, CTX)
    else:
        assert evaluate(expr, CTX) == value


def test_render_interpolates_each_expression():
    assert render('refs/tags/v${{ inputs.version }}', CTX) == 'refs/tags/v3.0-rc1'
    assert render('${{ github.event_name }}-${{ github.ref_name }}', CTX) == 'push-sextant'
    assert render('plain', CTX) == 'plain'
