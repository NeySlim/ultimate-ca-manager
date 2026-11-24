"""What the WinRM channel reads back from the CA: accents intact, no pywinrm warning per command.

The real pywinrm Session, Protocol and Transport run with their network faked (as in
test_msca_kerberos_keytab), so the script sent and the bytes returned are the CA's.
"""
import base64
import re
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
    answer('Accès refusé'.encode('cp1252'), b'', 1)
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


# --- what PowerShell itself reports ----------------------------------------------------------

def _clixml(*errors, progress='Préparation des modules à la première utilisation.'):
    """A stderr CLIXML block as powershell.exe writes it under WinRM: a progress record, then one
    ``<S S="Error">`` per line of the error record, CRLF escaped as ``_x000D__x000A_``."""
    records = ''.join(f'<S S="Error">{line}_x000D__x000A_</S>' for line in errors)
    return ('#< CLIXML\r\n<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">'
            '<Obj S="progress" RefId="0"><TN RefId="0"><T>System.Management.Automation.PSCustomObject</T>'
            f'<T>System.Object</T></TN><MS><I64 N="SourceId">1</I64><PR N="Record"><AV>{progress}</AV>'
            '<AI>0</AI><Nil /><PI>-1</PI><PC>-1</PC><T>Completed</T><SR>-1</SR><SD> </SD></PR></MS></Obj>'
            f'{records}</Objs>')


PARSE_ERROR = ('Au caractère Ligne:1 : 60', "+ ... certutil -view -restrict &quot;RequestId=1&quot; &amp; 'x",
               "Le terminateur ' est manquant dans la chaîne.",
               '    + CategoryInfo          : ParserError: (:) [], ParentContainsErrorRecordException',
               '    + FullyQualifiedErrorId : TerminatorExpectedAtEndOfString')


@pytest.mark.parametrize('encoding', ['cp437', 'utf-8'])
def test_a_powershell_error_is_read_from_its_clixml_records(answer, kerberos, encoding):  # noqa: F811
    """A parse error or an exception is only in the CLIXML stream, in the console's OEM code page."""
    from services.msca.admin_channel import MSCAAdminChannelError
    answer(b'', _clixml(*PARSE_ERROR).encode(encoding), 1)
    with pytest.raises(MSCAAdminChannelError) as raised:
        _run_ps(_channel_row(kerberos.keytab))
    message = str(raised.value)
    assert message.startswith('certutil failed (rc=1): Au caractère Ligne:1 : 60\n'), message
    assert "Le terminateur ' est manquant dans la chaîne." in message
    assert '-restrict "RequestId=1" & \'x' in message
    assert '_x000D_' not in message and '<S' not in message and 'CLIXML' not in message
    assert 'Préparation' not in message


def test_a_certutil_failure_beside_a_progress_stream_reads_its_output(answer, kerberos):  # noqa: F811
    """certutil writes its own failure on stdout, in the ANSI code page; stderr holds progress only."""
    from services.msca.admin_channel import MSCAAdminChannelError
    answer('CertUtil: -view ÉCHEC de la commande : Paramètre incorrect.'.encode('cp1252'),
           _clixml().encode('cp437'), 1)
    with pytest.raises(MSCAAdminChannelError) as raised:
        _run_ps(_channel_row(kerberos.keytab))
    assert str(raised.value) == 'certutil failed (rc=1): CertUtil: -view ÉCHEC de la commande : Paramètre incorrect.'


def test_a_plain_stderr_in_the_oem_code_page_keeps_its_accents(answer, kerberos):  # noqa: F811
    from services.msca.admin_channel import MSCAAdminChannelError
    answer(b'', 'Accès refusé à la chaîne'.encode('cp437'), 1)
    with pytest.raises(MSCAAdminChannelError, match='Accès refusé à la chaîne'):
        _run_ps(_channel_row(kerberos.keytab))


def test_the_message_of_a_long_powershell_error_is_bounded(answer, kerberos):  # noqa: F811
    from services.msca.admin_channel import MSCAAdminChannelError
    answer(b'', _clixml(*(['é' * 100] * 20)).encode('cp437'), 1)
    with pytest.raises(MSCAAdminChannelError) as raised:
        _run_ps(_channel_row(kerberos.keytab))
    assert len(str(raised.value)) <= len('certutil failed (rc=1): ') + 400


# --- no script reads certutil's output through PowerShell --------------------------------------

_CERTUTIL = re.compile(r'\bcertutil(?:\.exe)?\b', re.I)
_UNICODE_CONSOLE = '[Console]::OutputEncoding=[Text.Encoding]::Unicode'


def captured_certutil(script):
    """The statements where PowerShell reads certutil's output (assigned, in parentheses or piped):
    it decodes the ANSI bytes as UTF-8 and loses every accent before WinRM sees them. Allowed only
    as ``[Console]::OutputEncoding=[Text.Encoding]::Unicode; ... certutil -Unicode ...``."""
    found = []
    for statement in re.split(r'[;\r\n]', script):
        match = _CERTUTIL.search(statement)
        if not match:
            continue
        before, after = statement[:match.start()], statement[match.end():]
        if not ('=' in before or '(' in before or '|' in after):
            continue
        safe = (_UNICODE_CONSOLE in script[:script.find(statement)]
                and re.search(r'(?:^|\s)-Unicode\b', after, re.I))
        if not safe:
            found.append(statement.strip())
    return found


@pytest.mark.parametrize('script, found', [
    ("$ErrorActionPreference='Stop';chcp 65001 | Out-Null;certutil -config \"dc\\CA\" -view csv", []),
    ("$svc=(Get-Service certsvc).Status;certutil -ping;Write-Output \"UCM_CERTSVC=$svc\"", []),
    ('certutil -view -restrict "RequestId=4" -out "RawCertificate"', []),
    ('$o = certutil -view csv;$o', ['$o = certutil -view csv']),
    ('$o=(certutil.exe -view csv)', ['$o=(certutil.exe -view csv)']),
    ('certutil -view csv | Out-String', ['certutil -view csv | Out-String']),
    ('Write-Output (CertUtil -ping)', ['Write-Output (CertUtil -ping)']),
    ('$o = certutil -Unicode -view csv', ['$o = certutil -Unicode -view csv']),
    ('$e=[Console]::OutputEncoding;[Console]::OutputEncoding=[Text.Encoding]::Unicode;'
     '$o = certutil -Unicode -view csv;[Console]::OutputEncoding=$e;$o', []),
])
def test_the_capture_guard(script, found):
    assert captured_certutil(script) == found


@pytest.fixture
def channel(app, answer, kerberos, monkeypatch):  # noqa: F811
    """A saved connection whose WinRM channel signs in with Kerberos; every network call but
    WinRM refused. Yields its id inside an app context."""
    import uuid
    from models import db
    from models.msca import MicrosoftCA
    from services.msca.connection import MicrosoftCAConnectionMixin
    from services.msca.crl_sync import MicrosoftCACRLSyncMixin

    def offline(*args, **kwargs):
        raise RuntimeError('offline')
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client', staticmethod(offline))
    monkeypatch.setattr(MicrosoftCACRLSyncMixin, '_resolve_crl_url', staticmethod(offline))
    answer(b'')
    with app.app_context():
        row = MicrosoftCA(name=f'winrm-{uuid.uuid4().hex[:8]}', server='ca.example', auth_method='kerberos',
                          kerberos_principal='svc@CORP', kerberos_keytab_path=kerberos.keytab, enabled=True,
                          winrm_enabled=True, winrm_transport='kerberos', winrm_host='ca.example',
                          winrm_use_ssl=True, winrm_port=5986, ca_config='dc.corp\\Corp CA')
        db.session.add(row)
        db.session.commit()
        try:
            yield row
        finally:
            db.session.rollback()
            MicrosoftCA.query.filter_by(id=row.id).delete()
            db.session.commit()


def test_no_script_sent_reads_certutil_output_through_powershell(channel, answer):
    """Every script the channel sends, read from the WinRM command it becomes."""
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin as Admin
    from services.msca.ca_control import MicrosoftCACAControlMixin as Control
    from services.msca.inventory import MicrosoftCAInventoryMixin as Inventory
    Admin.test_admin_channel_config(channel)
    Admin.publish_crl(channel.id)
    Admin.revoke_on_ca(channel, '1a2b', 'keyCompromise')
    Admin.revoke_on_ca(channel, '1a2b', publish_crl=False)
    Admin.unrevoke_on_ca(channel, '1a2b')
    Control.list_pending_requests(channel.id)
    Control.approve_request(channel.id, 7)
    Control.deny_request(channel.id, 7)
    Control.ca_health(channel.id)
    Inventory._list_issued(channel, 0)
    Inventory._fetch_cert_pem(channel, 7)
    Inventory._deny_refused(channel, {7: None})
    Inventory.reconcile_inventory(channel.id)
    verbs = {v for s in answer.scripts for v in re.findall(r'certutil [^;]*?(-ping|-crl|-revoke|-view|-resubmit|-deny)', s)}
    assert verbs == {'-ping', '-crl', '-revoke', '-view', '-resubmit', '-deny'}
    assert [c for s in answer.scripts for c in captured_certutil(s)] == []
