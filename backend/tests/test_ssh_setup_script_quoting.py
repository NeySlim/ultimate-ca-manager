"""An SSH CA description reaches the served setup scripts as text, never as code: a single-quoted
literal in sh and PowerShell, a one-line comment, whatever the description holds."""
import json
import os
import re
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from api.v2.ssh.setup_scripts import _generate_setup_script
from models import db
from models.ssh import SSHCertificateAuthority
from tests.conftest import get_json
from tests.ssh_cleanup import ssh_rows_stay_in_their_module  # noqa: F401

PUB = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl'
SHELLS = [s for s in ('sh', 'bash', 'dash') if shutil.which(s)]
PS_QUOTES = "'‘’‚‛"


def _trap(marker_dir):
    """A description that runs `touch` in marker_dir by every way out of a quoted string."""
    m = str(marker_dir)
    return (f'Ops CA $(touch {m}/subst) `touch {m}/tick` "dq" \'sq\' ’smart’ '
            f'$env:PATH `$(New-Item {m}/ps) #> <#\nnext line; touch {m}/newline\r\x0bend')


def _one_line(text):
    return re.sub(r'[\x00-\x1f\x7f\x85  ]', ' ', text)


def _prefix_up_to_the_label(script):
    """Header, settings, helpers and the banner that prints the CA: nothing that writes a file."""
    return script[:script.index('if [ "$DRY_RUN" = true ]; then')]


def _run_banner(shell, script, tmp_path):
    stub = tmp_path / 'bin'
    stub.mkdir(exist_ok=True)
    for name, out in (('id', '0'), ('hostname', 'web01.example.com')):
        (stub / name).write_text(f'#!/bin/sh\necho {out}\n')
        (stub / name).chmod(0o755)
    env = {'PATH': f'{stub}:{os.environ.get("PATH", "/usr/bin:/bin")}', 'HOME': str(tmp_path)}
    return subprocess.run([shell, '-c', _prefix_up_to_the_label(script), 'setup'], capture_output=True,
                          text=True, cwd=tmp_path, env=env, timeout=30)


def _no_marker(marker_dir):
    assert sorted(os.listdir(marker_dir)) == [], 'the description ran as a command'


@pytest.mark.skipif(not SHELLS, reason='no POSIX shell')
@pytest.mark.parametrize('ca_type', ['user', 'host'])
def test_the_unix_script_prints_the_description_and_runs_none_of_it(tmp_path, ca_type):
    marker = tmp_path / 'markers'
    marker.mkdir()
    descr = _trap(marker)
    script = _generate_setup_script(SimpleNamespace(descr=descr, id=7), PUB, ca_type, '', 'unix')
    for shell in SHELLS:
        assert subprocess.run([shell, '-n', '-c', script], capture_output=True).returncode == 0, shell
        run = _run_banner(shell, script, tmp_path)
        _no_marker(marker)
        assert run.returncode == 0, (shell, run.stderr)
        assert f'CA: {_one_line(descr)}\n' in run.stdout, (shell, run.stdout)
    comment = [line for line in script.splitlines() if line.startswith('# CA: ')]
    assert comment == [f'# CA: {_one_line(descr)}']


def _ps_literal_value(literal):
    """The value of a PowerShell single-quoted string: two quote characters stand for one."""
    assert literal[0] in PS_QUOTES and literal[-1] in PS_QUOTES
    body, out, i = literal[1:-1], [], 0
    while i < len(body):
        if body[i] in PS_QUOTES:
            assert i + 1 < len(body) and body[i + 1] in PS_QUOTES, 'a lone quote ends the literal'
            i += 1
        out.append(body[i])
        i += 1
    return ''.join(out)


def _ps_value(expr):
    """The value of a quoted literal, or of ('literal' + [char]0xHHHH + ...) with ASCII literals."""
    assert expr.isascii(), 'a non-ASCII byte may read as a quote in an ANSI code page'
    if not expr.startswith('('):
        return _ps_literal_value(expr)
    assert expr.endswith(')')
    parts = re.findall(r"'(?:[^']|'')*'|\[char\]0x[0-9A-F]{4}", expr[1:-1])
    assert ' + '.join(parts) == expr[1:-1] and parts[0].startswith("'")
    units = ''.join(chr(int(p[8:], 16)) if p.startswith('[') else _ps_literal_value(p) for p in parts)
    return units.encode('utf-16-le', 'surrogatepass').decode('utf-16-le')


@pytest.mark.parametrize('ca_type', ['user', 'host'])
def test_the_powershell_script_holds_the_description_as_a_literal(tmp_path, ca_type):
    descr = _trap(tmp_path)
    script = _generate_setup_script(SimpleNamespace(descr=descr, id=7), PUB, ca_type, '', 'windows')
    shown = _one_line(descr)
    banner = re.findall(r"^Write-Host \('CA:\s*' \+ (.*)\)$", script, re.M)
    assert len(banner) == 1, 'the CA banner is not a single-quoted literal'
    assert _ps_value(banner[0]) == shown
    # The help block stays closed until its own #>, the label sits on one line inside it
    help_block = script[:script.index('#>')]
    assert '.EXAMPLE' in help_block
    assert [line.strip() for line in help_block.splitlines() if line.strip().startswith('CA: ')] \
        == [f'CA: {shown.replace("#>", "# >")}']
    # Nowhere else: no double-quoted string ever holds it
    assert script.count(f'New-Item {tmp_path}/ps') == 2


@pytest.mark.parametrize('descr', ['G\u0142\u00f3wny CA', 'K\u0151) ; New-Item C:\\pwned #', 'emoji \U0001F511 CA'])
@pytest.mark.parametrize('ca_type', ['user', 'host'])
def test_powershell_code_stays_ascii_for_a_non_ascii_description(ca_type, descr):
    """Windows PowerShell 5.1 reads a BOM-less .ps1 in the ANSI code page, where UTF-8 bytes
    of a letter can decode to a quote: outside the help comment the script is pure ASCII."""
    script = _generate_setup_script(SimpleNamespace(descr=descr, id=7), PUB, ca_type, 'h\u00f6st', 'windows')
    code = script[script.index('#>'):]
    assert code.isascii()
    banner = re.findall(r"^Write-Host \('CA:\s*' \+ (.*)\)$", script, re.M)
    assert len(banner) == 1 and _ps_value(banner[0]) == descr
    if ca_type == 'host':
        literal = re.findall(r'^\$Hostname\s+= (.*)$', script, re.M)
        assert len(literal) == 1 and _ps_value(literal[0]) == 'h\u00f6st'


@pytest.mark.skipif(not shutil.which('pwsh'), reason='pwsh not available')
@pytest.mark.parametrize('ca_type', ['user', 'host'])
def test_pwsh_parses_the_script_and_prints_the_description(tmp_path, ca_type):
    descr = _trap(tmp_path)
    script = _generate_setup_script(SimpleNamespace(descr=descr, id=7), PUB, ca_type, '', 'windows')
    banner = re.search(r"^Write-Host \('CA:.*$", script, re.M).group(0)
    check = ("$e=$null;[void][System.Management.Automation.Language.Parser]::ParseInput("
             "[IO.File]::ReadAllText($args[0]),[ref]$null,[ref]$e);if($e){exit 3};"
             f"{banner}")
    path = tmp_path / 's.ps1'
    path.write_text(script, encoding='utf-8')
    run = subprocess.run(['pwsh', '-NoProfile', '-Command', check, str(path)], capture_output=True,
                         text=True, cwd=tmp_path, timeout=60)
    assert run.returncode == 0, run.stderr
    assert not (tmp_path / 'ps').exists()
    assert _one_line(descr) in run.stdout


def _create(auth_client, descr, ca_type='user'):
    return auth_client.post('/api/v2/ssh/cas', data=json.dumps(
        {'descr': descr, 'ca_type': ca_type, 'key_type': 'ed25519'}), content_type='application/json')


@pytest.mark.skipif(not SHELLS, reason='no POSIX shell')
def test_the_public_route_serves_a_stored_description_as_text(app, auth_client, tmp_path):
    marker = tmp_path / 'markers'
    marker.mkdir()
    r = _create(auth_client, f'Ops CA $(touch {marker}/subst) `touch {marker}/tick` "dq"')
    assert r.status_code == 201, r.data
    ca = get_json(r)['data']
    # A row written before the input check (or restored) may hold a line break
    with app.app_context():
        row = db.session.get(SSHCertificateAuthority, ca['id'])
        row.descr = _trap(marker)
        db.session.commit()
    windows = app.test_client().get(f"/ssh/setup/{ca['refid']}?platform=windows")
    assert windows.status_code == 200
    assert re.search(r"^Write-Host \('CA:\s*' \+ \('", windows.data.decode(), re.M)
    script = app.test_client().get(f"/ssh/setup/{ca['refid']}").data.decode()
    run = _run_banner(SHELLS[0], script, tmp_path)
    _no_marker(marker)
    assert run.returncode == 0, run.stderr


@pytest.mark.parametrize('bad', ['two\nlines', 'tab\there', 'cr\rhere', 'nul\x00here', 'sep here'])
def test_a_description_with_a_control_character_is_refused(app, auth_client, bad):
    assert _create(auth_client, bad).status_code == 400
    r = _create(auth_client, 'Plain SSH CA')
    assert r.status_code == 201, r.data
    ca_id = get_json(r)['data']['id']
    put = auth_client.put(f'/api/v2/ssh/cas/{ca_id}', data=json.dumps({'descr': bad}),
                          content_type='application/json')
    assert put.status_code == 400
    with app.app_context():
        assert db.session.get(SSHCertificateAuthority, ca_id).descr == 'Plain SSH CA'
    imp = auth_client.post('/api/v2/ssh/cas/import', data=json.dumps(
        {'descr': bad, 'private_key': 'not parsed before the description', 'ca_type': 'user'}),
        content_type='application/json')
    assert imp.status_code == 400 and b'control' in imp.data
