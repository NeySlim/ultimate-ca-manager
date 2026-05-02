from .utils import SSHCertificateUtilsMixin
from .signing import SSHCertificateSigningMixin
from .decode import SSHCertificateDecodeMixin
from .management import SSHCertificateManagementMixin

# Module-level constant preserved for backward compatibility
USER_EXTENSIONS = {
    'permit-pty': b'',
    'permit-user-rc': b'',
    'permit-agent-forwarding': b'',
    'permit-port-forwarding': b'',
    'permit-X11-forwarding': b'',
}


class SSHCertificateService(
    SSHCertificateUtilsMixin,
    SSHCertificateSigningMixin,
    SSHCertificateDecodeMixin,
    SSHCertificateManagementMixin,
):
    pass
