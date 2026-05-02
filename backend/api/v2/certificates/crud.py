"""
Certificates CRUD Routes

Aggregator — imports all route submodules to register them on the blueprint.
Split into focused modules for maintainability.
"""
from . import (  # noqa: F401
    cert_list,
    cert_create,
    cert_get,
    cert_lifecycle,
    cert_upload,
    cert_renew,
    cert_import,
)
