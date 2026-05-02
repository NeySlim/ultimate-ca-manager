from .connection import MicrosoftCAConnectionMixin
from .templates import MicrosoftCATemplatesMixin
from .certs import MicrosoftCACertsMixin
from .requests import MicrosoftCARequestsMixin


class MicrosoftCAService(
    MicrosoftCAConnectionMixin,
    MicrosoftCATemplatesMixin,
    MicrosoftCACertsMixin,
    MicrosoftCARequestsMixin,
):
    pass
