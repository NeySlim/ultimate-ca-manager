# backward-compat shim — use services.opnsense instead
from services.opnsense import OPNsenseImportService, get_import_config, save_import_config  # noqa: F401

__all__ = ['OPNsenseImportService', 'get_import_config', 'save_import_config']
