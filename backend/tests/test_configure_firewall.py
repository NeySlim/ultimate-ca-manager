"""configure-firewall.sh changes the firewall only on UCM_FIREWALL=yes: it never prompts."""
import pathlib
import subprocess

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / 'packaging' / 'scripts' / 'configure-firewall.sh'


def _choice(tmp_path, value):
    text = SCRIPT.read_text()
    # Its functions only: the call of main, which would configure this machine, is cut off
    assert text.count('\nmain "$@"\n') == 1
    lib = tmp_path / 'fw-functions.sh'
    lib.write_text(text.replace('\nmain "$@"\n', '\n'))
    env = {'PATH': '/usr/bin:/bin'}
    if value is not None:
        env['UCM_FIREWALL'] = value
    out = subprocess.run(['bash', '-c', f'. {lib}; get_firewall_choice'], env=env, input='y\n',
                         capture_output=True, text=True, timeout=10)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


@pytest.mark.parametrize('value, choice', [
    ('yes', 'yes'), ('1', 'yes'), ('no', 'no'), (None, 'no'),
    # Nothing can ask: a value that is not a yes leaves the firewall as it is
    ('ask', 'no'), ('maybe', 'no'),
])
def test_only_an_explicit_yes_opens_the_firewall(tmp_path, value, choice):
    assert _choice(tmp_path, value) == choice
