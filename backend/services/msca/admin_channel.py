"""WinRM administration channel for Microsoft CA connections (#185 phase A).

Runs CA management operations (revoke, unrevoke, publish CRL, and later
inventory) on the Windows CA through PowerShell remoting + ``certutil``.

Opt-in per connection. ``pywinrm`` is an OPTIONAL dependency, lazy-imported
here so the rest of UCM (and installs without AD CS) never require it — same
rule as ``certsrv`` and ``pkilint``.
"""
import html
import logging
import re
import warnings

from models import db
from models.msca import MicrosoftCA
from utils.datetime_utils import utc_now
from services.msca import kerberos as _kerberos
from services.msca.kerberos import KerberosAuth, MSCAKerberosError, gssapi_available, initiator_credential

logger = logging.getLogger(__name__)

# UCM revocation reason → certutil numeric reason code.
_CERTUTIL_REASON = {
    'unspecified': 0,
    'keyCompromise': 1,
    'CACompromise': 2,
    'affiliationChanged': 3,
    'superseded': 4,
    'cessationOfOperation': 5,
    'certificateHold': 6,
}

# certutil unrevoke sentinel (only lifts a certificateHold).
_CERTUTIL_UNREVOKE = -1

_SERIAL_RE = re.compile(r'^[0-9a-fA-F]+$')
# Only what PowerShell writes itself turns UTF-8: certutil writes its ANSI code page (cp1252) and
# the WinRM console is OEM 437. Never capture certutil's output (PowerShell would decode it wrongly)
_UTF8_OUTPUT = 'try{[Console]::OutputEncoding=New-Object Text.UTF8Encoding $false}catch{};'
# What the Kerberos sign-in needs of a pywinrm 0.5.0 Transport
_PYWINRM_TRANSPORT = ('message_encryption', 'endpoint', 'build_session', 'setup_encryption', 'auth_method')


def _decode(data):
    """WinRM output as text: UTF-8 as asked, else the Windows ANSI code page it may still be in."""
    try:
        return (data or b'').decode('utf-8').lstrip('\ufeff')
    except UnicodeDecodeError:
        return data.decode('cp1252', errors='replace')


def _decode_stderr(data):
    """stderr as text: UTF-8 when pywinrm re-encoded it, else the OEM code page of the console."""
    try:
        return (data or b'').decode('utf-8').lstrip('\ufeff')
    except UnicodeDecodeError:
        return data.decode('cp437')


_CLIXML_ERROR = re.compile(r'<S S="Error">(.*?)</S>', re.S)
_CLIXML_CHAR = re.compile(r'_x([0-9A-Fa-f]{4})_')


def _clixml_errors(text):
    """The lines of the error records in PowerShell's CLIXML stream: a parse error or an
    exception is only there. XML entities first, then PowerShell's ``_xHHHH_`` escapes."""
    lines = (_CLIXML_CHAR.sub(lambda m: chr(int(m.group(1), 16)), html.unescape(raw))
             for raw in _CLIXML_ERROR.findall(text))
    return ''.join(lines).replace('\r\n', '\n').strip()


def kerberos_transport_available() -> bool:
    """Whether the WinRM channel can sign in with Kerberos here (python-gssapi installed)."""
    return gssapi_available()


class MSCAAdminChannelError(Exception):
    """Raised for admin-channel configuration or remote-execution failures."""


class MicrosoftCAAdminChannelMixin:

    # --- Public operations -------------------------------------------------

    @staticmethod
    def admin_channel_available(msca):
        """True if the connection has an enabled, usable WinRM admin channel."""
        if not msca.winrm_enabled:
            return False
        if msca.winrm_transport == 'kerberos':
            # A keytab alone signs in as its first principal
            return bool(msca.kerberos_principal or msca.winrm_username or msca.kerberos_keytab_path)
        return bool(msca.winrm_effective_username and msca.winrm_effective_password)

    @staticmethod
    def test_admin_channel(msca_id):
        """Validate the WinRM channel: connect + confirm the CA service/config."""
        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            raise MSCAAdminChannelError('Connection not found')
        return MicrosoftCAAdminChannelMixin.test_admin_channel_config(msca)

    @staticmethod
    def test_admin_channel_config(config):
        """Validate a WinRM channel from a saved connection OR a transient
        config object (unsaved form overrides). Never persists anything —
        the object only needs the winrm_*/ca_config attributes and the
        winrm_effective_* values a MicrosoftCA row exposes.
        """
        script = (
            "$ErrorActionPreference='Stop';"
            "chcp 65001 | Out-Null;"
            "$svc=(Get-Service certsvc -ErrorAction SilentlyContinue).Status;"
            "certutil -ping;"
            "Write-Output \"UCM_CERTSVC=$svc\""
        )
        out = MicrosoftCAAdminChannelMixin._run_ps(config, script)
        svc = None
        m = re.search(r'UCM_CERTSVC=(\w+)', out)
        if m:
            svc = m.group(1)
        return {
            'success': True,
            'certsvc_status': svc,
            'transport': config.winrm_transport,
            'host': config.winrm_effective_host,
        }

    @staticmethod
    def revoke_on_ca(msca, serial_number, reason='unspecified', publish_crl=True):
        """Revoke a certificate on the Windows CA by serial number."""
        serial = MicrosoftCAAdminChannelMixin._validate_serial(serial_number)
        code = _CERTUTIL_REASON.get(reason, 0)
        return MicrosoftCAAdminChannelMixin._revoke_serial(msca, serial, code, publish_crl)

    @staticmethod
    def unrevoke_on_ca(msca, serial_number, publish_crl=True):
        """Lift a certificateHold on the Windows CA (certutil unrevoke)."""
        serial = MicrosoftCAAdminChannelMixin._validate_serial(serial_number)
        return MicrosoftCAAdminChannelMixin._revoke_serial(
            msca, serial, _CERTUTIL_UNREVOKE, publish_crl
        )

    @staticmethod
    def publish_crl(msca_id):
        """Force the CA to publish a fresh CRL (certutil -crl)."""
        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            raise MSCAAdminChannelError('Connection not found')
        config = MicrosoftCAAdminChannelMixin._config_arg(msca)
        script = (
            "$ErrorActionPreference='Stop';chcp 65001 | Out-Null;"
            f"certutil {config}-crl"
        )
        out = MicrosoftCAAdminChannelMixin._run_ps(msca, script)
        logger.info(f"MS CA '{msca.name}' published CRL via admin channel")
        return {'success': True, 'output': out.strip()[-500:]}

    # --- Internals ---------------------------------------------------------

    @staticmethod
    def _revoke_serial(msca, serial, reason_code, publish_crl):
        config = MicrosoftCAAdminChannelMixin._config_arg(msca)
        # serial is validated hex; reason_code is an int we control — no user
        # string reaches the shell.
        script = (
            "$ErrorActionPreference='Stop';chcp 65001 | Out-Null;"
            f"certutil {config}-revoke {serial} {reason_code}"
        )
        if publish_crl:
            script += f";certutil {config}-crl"
        out = MicrosoftCAAdminChannelMixin._run_ps(msca, script)
        return {'success': True, 'serial': serial, 'reason_code': reason_code,
                'output': out.strip()[-500:]}

    @staticmethod
    def _validate_serial(serial_number):
        if not serial_number:
            raise MSCAAdminChannelError('Serial number is required')
        serial = str(serial_number).strip().replace(':', '').lower()
        if not _SERIAL_RE.match(serial):
            raise MSCAAdminChannelError(f'Invalid serial number: {serial_number!r}')
        return serial

    @staticmethod
    def _config_arg(msca):
        """certutil -config "Machine\\CAName" prefix, or empty for local CA."""
        if not msca.ca_config:
            return ''
        # ca_config is an admin-set identifier; still refuse quotes/newlines
        # so it can't break out of the argument.
        cfg = msca.ca_config.strip()
        if any(c in cfg for c in '"\r\n`$;|&'):
            raise MSCAAdminChannelError('Invalid ca_config value')
        return f'-config "{cfg}" '

    @staticmethod
    def _build_session(msca):
        """Create a pywinrm Session from the connection's WinRM settings."""
        try:
            import winrm  # noqa: F401
        except ImportError:
            raise MSCAAdminChannelError(
                'WinRM admin channel requires the optional "pywinrm" package '
                '(pip install pywinrm)'
            )
        import winrm
        # pywinrm warns on every CLIXML progress stream it cannot parse; _run_ps reads stderr itself
        warnings.filterwarnings('ignore', message='There was a problem converting the Powershell error message',
                                category=UserWarning, module=r'winrm(\.|$)')

        host = msca.winrm_effective_host
        if not host:
            raise MSCAAdminChannelError('WinRM host is not configured')
        scheme = 'https' if msca.winrm_use_ssl else 'http'
        port = msca.winrm_port or (5986 if msca.winrm_use_ssl else 5985)
        endpoint = f'{scheme}://{host}:{port}/wsman'

        transport = (msca.winrm_transport or 'kerberos').lower()
        server_cert_validation = 'validate' if (msca.winrm_use_ssl and msca.winrm_verify_ssl) else 'ignore'

        if transport == 'kerberos':
            # The enrollment principal and keytab, unless the channel names its own account;
            # _run_ps gives the session the connection's own sign-in
            return winrm.Session(
                endpoint,
                auth=(msca.winrm_effective_username or msca.kerberos_principal or '', ''),
                transport='kerberos',
                server_cert_validation=server_cert_validation,
            )

        import fips_mode
        if fips_mode.enabled():
            # NTLM hashes with MD4/MD5 outside the FIPS module
            if kerberos_transport_available():
                problem = _kerberos.fips_crypto_problem()
                if problem is None:
                    raise MSCAAdminChannelError(
                        'NTLM is not available in FIPS mode: use the Kerberos transport')
                raise MSCAAdminChannelError(
                    f'NTLM is not available in FIPS mode and Kerberos cannot replace it here ({problem}): '
                    'turn off the WinRM channel of this connection')
            raise MSCAAdminChannelError(
                'NTLM is not available in FIPS mode and the Kerberos transport is not '
                'installed (pyspnego[kerberos]): turn off the WinRM channel of this connection')
        username = msca.winrm_effective_username
        password = msca.winrm_effective_password
        if not username or not password:
            raise MSCAAdminChannelError(
                'WinRM channel needs a username and password (set an override: the '
                'connection password is reused only on the CA host, and mTLS-enrolled '
                'connections have no reusable credential)'
            )
        return winrm.Session(
            endpoint,
            auth=(username, password),
            transport=transport,  # 'ntlm'
            server_cert_validation=server_cert_validation,
        )

    @staticmethod
    def _bind_kerberos(session, msca):
        """Give pywinrm's HTTP session the connection's own Kerberos sign-in.

        pywinrm 0.5.0 signs in through pykerberos and the process' ticket cache; the session is
        built here without any authentication, then gets a KerberosAuth on the connection's
        credential (preemptive, mutual authentication required, as pywinrm asks), and the message
        encryption is set up as build_session would have.
        """
        _kerberos.refuse_outside_fips_module()  # before the first WinRM message
        transport = getattr(getattr(session, 'protocol', None), 'transport', None)
        if transport is None or getattr(transport, 'session', True) is not None or not all(
                hasattr(transport, name) for name in _PYWINRM_TRANSPORT):
            raise MSCAAdminChannelError('This pywinrm version is not supported for the Kerberos transport')
        wanted = transport.message_encryption
        transport.auth_method, transport.message_encryption = 'plaintext', 'never'
        try:
            http = transport.build_session()
        finally:
            transport.auth_method, transport.message_encryption = 'kerberos', wanted
        if transport.session is not http:
            raise MSCAAdminChannelError('This pywinrm version is not supported for the Kerberos transport')
        principal = msca.winrm_effective_username or msca.kerberos_principal or None
        keytab = msca.kerberos_keytab_path or None
        # A saved connection keeps its credential; a channel test of form values keeps nothing
        kept = msca.id if isinstance(msca, MicrosoftCA) else None
        http.auth = KerberosAuth(
            lambda: initiator_credential(kept, principal, keytab, channel='winrm'),
            mutual_required=True, preemptive=True, service=getattr(transport, 'service', 'HTTP') or 'HTTP',
            hostname_override=getattr(transport, 'kerberos_hostname_override', None),
            delegate=bool(getattr(transport, 'kerberos_delegation', False)),
            send_cbt=bool(getattr(transport, 'send_cbt', True)))
        if wanted == 'always' or (wanted == 'auto' and not transport.endpoint.lower().startswith('https')):
            transport.setup_encryption(http)

    @staticmethod
    def _run_ps(msca, script):
        """Run a PowerShell script on the CA; raise on non-zero exit.

        PowerShell writes a CLIXML progress stream to stderr even on success,
        so stderr is only surfaced when the exit code is non-zero.
        """
        session = MicrosoftCAAdminChannelMixin._build_session(msca)
        try:
            if (msca.winrm_transport or 'kerberos').lower() == 'kerberos':
                MicrosoftCAAdminChannelMixin._bind_kerberos(session, msca)
            result = session.run_ps(_UTF8_OUTPUT + script)
        except MSCAAdminChannelError:
            raise
        except MSCAKerberosError as e:
            raise MSCAAdminChannelError(str(e)) from None
        except ValueError as e:  # a keytab UCM manages itself
            raise MSCAAdminChannelError(str(e)) from None
        except Exception as e:
            raise MSCAAdminChannelError(f'WinRM execution failed: {e}')

        stdout = _decode(result.std_out)
        if result.status_code != 0:
            stderr = _decode_stderr(result.std_err)
            # The CLIXML stream is dropped but for its error records, never its progress records
            errors = _clixml_errors(stderr)
            stderr = re.sub(r'#< CLIXML.*', '', stderr, flags=re.S).strip()
            msg = ('\n'.join(t for t in (stderr, errors) if t) or stdout).strip()[:400]
            raise MSCAAdminChannelError(f'certutil failed (rc={result.status_code}): {msg}')
        return stdout
