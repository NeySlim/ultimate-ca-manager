"""What the WinRM channel reads back from the CA: accents intact, no pywinrm warning per command.

The real pywinrm Session, Protocol and Transport run with their network faked (as in
test_msca_kerberos_keytab), so the script sent and the bytes returned are the CA's.
"""
import base64
import warnings

import pytest

from tests.test_msca_kerberos_keytab import _channel_row, _run_ps, kerberos, pywinrm  # noqa: F401

FRENCH = 'Authentification du contrôleur de domaine, Refusé'


@pytest.fixture
def answer(monkeypatch, pywinrm):  # noqa: F811
    """``answer(stdout, stderr=b'', rc=0)`` sets what the CA returns; the scripts sent are kept."""
    import winrm.protocol
    scripts = []

    def run_command(self, shell_id, command, args=()):
        scripts.append(base64.b64decode(command.split()[-1]).decode('utf-16-le'))
        return 'command'
    monkeypatch.setattr(winrm.protocol.Protocol, 'run_command', run_command)

    def set_answer(stdout, stderr=b'', rc=0):
        monkeypatch.setattr(winrm.protocol.Protocol, 'get_command_output',
                            lambda self, shell_id, command_id: (stdout, stderr, rc))
    set_answer.scripts = scripts
    return set_answer


def test_each_script_asks_powershell_for_utf8_output(answer, kerberos):  # noqa: F811
    answer(b'ok')
    _run_ps(_channel_row(kerberos.keytab))
    script, = answer.scripts
    assert script.startswith('try{[Console]::OutputEncoding=New-Object Text.UTF8Encoding $false}catch{};')
    assert script.endswith(';x')


@pytest.mark.parametrize('encoding', ['utf-8', 'cp1252'])
def test_accents_survive_whichever_encoding_the_ca_answers_in(answer, kerberos, encoding):  # noqa: F811
    answer(FRENCH.encode(encoding))
    assert _run_ps(_channel_row(kerberos.keytab)) == FRENCH


def test_a_failure_message_keeps_its_accents(answer, kerberos):  # noqa: F811
    from services.msca.admin_channel import MSCAAdminChannelError
    answer(b'', 'Accès refusé'.encode('cp1252'), 1)
    with pytest.raises(MSCAAdminChannelError, match='Accès refusé'):
        _run_ps(_channel_row(kerberos.keytab))


def test_the_progress_stream_of_a_successful_command_raises_no_warning(answer, kerberos):  # noqa: F811
    """PowerShell writes a CLIXML progress stream to stderr; pywinrm warns when it cannot parse it."""
    answer(b'ok', b'#< CLIXML\r\n<Objs Version="1.1.0.1"><Obj S="progress"', 0)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        assert _run_ps(_channel_row(kerberos.keytab)) == 'ok'
    assert [str(w.message) for w in caught if 'Powershell error message' in str(w.message)] == []


def test_other_warnings_of_pywinrm_are_kept(answer, kerberos):  # noqa: F811
    answer(b'ok')
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        _run_ps(_channel_row(kerberos.keytab))
        import winrm
        warnings.warn_explicit('another pywinrm warning', UserWarning, winrm.__file__, 1, module='winrm')
    assert 'another pywinrm warning' in [str(w.message) for w in caught]
