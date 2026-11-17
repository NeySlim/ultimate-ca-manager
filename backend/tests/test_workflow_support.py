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
    ("${{ format('x') }}", 'x'),
    ("format('refs/tags/v{0}', inputs.version)", 'refs/tags/v3.0-rc1'),
    ("format('{0}/{1}', 'a', needs.build-deb.outputs.version)", 'a/3.0'),
    ("format('{{0}}{0}', true)", '{0}true'),
    ("fromJSON('x')", ValueError),
    ("${{ inputs.version }}", '3.0-rc1'),
    ("needs.build-deb.outputs.version", '3.0'),
    ("github.event.workflow_run.head_branch", None),
    ("cancelled()", False),
    ("unknown.thing", ValueError),
    ("refs/tags/v${{ inputs.version }}", ValueError),
    ("!github.event_name == 'push'", ValueError),  # GitHub reads (!a) == b: refused, never guessed
    ("!!github.event_name != 'push'", ValueError),
    ("!github.event_name", False),
    ("!!github.event_name", True),
    ("!cancelled() && github.event_name == 'push'", True),
    ("(!github.event_name) == false", True),
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
