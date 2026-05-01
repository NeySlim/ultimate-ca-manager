"""
OPNsense Import Service package — imports Trust data from OPNsense.
"""
from .connection import ConnectionMixin
from .parser import ParserMixin
from .importer import ImportMixin


class OPNsenseImportService(ConnectionMixin, ParserMixin, ImportMixin):
    """Service for importing Trust data from OPNsense."""

    def __init__(self, base_url: str, username: str = None, password: str = None,
                 api_key: str = None, api_secret: str = None,
                 verify_ssl: bool = False):
        """
        Initialize OPNsense import service.

        Supports two authentication methods:
        1. Username/Password (legacy web scraping method)
        2. API Key/Secret (REST API method — recommended)

        Args:
            base_url: OPNsense base URL (e.g., https://192.168.1.1)
            username: OPNsense username (for web scraping auth)
            password: OPNsense password (for web scraping auth)
            api_key: OPNsense API key (for REST API auth — recommended)
            api_secret: OPNsense API secret (for REST API auth — recommended)
            verify_ssl: Verify SSL certificate (default False for self-signed)
        """
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.api_key = api_key
        self.api_secret = api_secret
        self.verify_ssl = verify_ssl
        self.session = None

        self.use_api = bool(api_key and api_secret)

        if not self.use_api and not (username and password):
            raise ValueError("Must provide either username/password or api_key/api_secret")


from .config import get_import_config, save_import_config  # noqa: E402

__all__ = ['OPNsenseImportService', 'get_import_config', 'save_import_config']
