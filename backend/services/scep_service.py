"""
Backward-compatibility shim — SCEP service has moved to services/scep/.
"""
from services.scep.scep_service import SCEPService  # noqa: F401

__all__ = ['SCEPService']
