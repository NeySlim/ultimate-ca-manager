"""WinRM administration channel for Microsoft CA connections (#185 phase A).

Runs CA management operations (revoke, unrevoke, publish CRL, and later
inventory) on the Windows CA through PowerShell remoting + ``certutil``.

Opt-in per connection. ``pywinrm`` is an OPTIONAL dependency, lazy-imported
here so the rest of UCM (and installs without AD CS) never require it — same
rule as ``certsrv`` and ``pkilint``.
"""
import logging
import re

from models import db
from models.msca import MicrosoftCA
from utils.datetime_utils import utc_now

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
            return bool(msca.kerberos_principal or msca.winrm_username)
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

        host = msca.winrm_effective_host
        if not host:
            raise MSCAAdminChannelError('WinRM host is not configured')
        scheme = 'https' if msca.winrm_use_ssl else 'http'
        port = msca.winrm_port or (5986 if msca.winrm_use_ssl else 5985)
        endpoint = f'{scheme}://{host}:{port}/wsman'

        transport = (msca.winrm_transport or 'kerberos').lower()
        server_cert_validation = 'validate' if (msca.winrm_use_ssl and msca.winrm_verify_ssl) else 'ignore'

        if transport == 'kerberos':
            # Kerberos reuses the enroll keytab/principal already on the host.
            import os
            if msca.kerberos_keytab_path:
                os.environ['KRB5_CLIENT_KTNAME'] = msca.kerberos_keytab_path
            return winrm.Session(
                endpoint,
                auth=(msca.winrm_effective_username or '', ''),
                transport='kerberos',
                server_cert_validation=server_cert_validation,
            )

        username = msca.winrm_effective_username
        password = msca.winrm_effective_password
        if not username or not password:
            raise MSCAAdminChannelError(
                'WinRM channel needs a username and password (set an override; '
                'mTLS-enrolled connections have no reusable credential)'
            )
        return winrm.Session(
            endpoint,
            auth=(username, password),
            transport=transport,  # 'ntlm'
            server_cert_validation=server_cert_validation,
        )

    @staticmethod
    def _run_ps(msca, script):
        """Run a PowerShell script on the CA; raise on non-zero exit.

        PowerShell writes a CLIXML progress stream to stderr even on success,
        so stderr is only surfaced when the exit code is non-zero.
        """
        session = MicrosoftCAAdminChannelMixin._build_session(msca)
        try:
            result = session.run_ps(script)
        except Exception as e:
            raise MSCAAdminChannelError(f'WinRM execution failed: {e}')

        stdout = (result.std_out or b'').decode('utf-8', errors='replace')
        if result.status_code != 0:
            stderr = (result.std_err or b'').decode('utf-8', errors='replace')
            # Strip the CLIXML noise for a readable error.
            stderr = re.sub(r'#< CLIXML.*', '', stderr, flags=re.S).strip()
            msg = (stderr or stdout).strip()[:400]
            raise MSCAAdminChannelError(f'certutil failed (rc={result.status_code}): {msg}')
        return stdout
