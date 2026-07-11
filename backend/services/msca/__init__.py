from .connection import MicrosoftCAConnectionMixin
from .templates import MicrosoftCATemplatesMixin
from .certs import MicrosoftCACertsMixin
from .requests import MicrosoftCARequestsMixin
from .crl_sync import MicrosoftCACRLSyncMixin
from .admin_channel import MicrosoftCAAdminChannelMixin, MSCAAdminChannelError
from .inventory import MicrosoftCAInventoryMixin
from .ca_control import MicrosoftCACAControlMixin


class MicrosoftCAService(
    MicrosoftCAConnectionMixin,
    MicrosoftCATemplatesMixin,
    MicrosoftCACertsMixin,
    MicrosoftCARequestsMixin,
    MicrosoftCACRLSyncMixin,
    MicrosoftCAAdminChannelMixin,
    MicrosoftCAInventoryMixin,
    MicrosoftCACAControlMixin,
):
    pass
