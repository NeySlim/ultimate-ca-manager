"""Backward-compatible shim — implementation lives in services/cert/"""
from services.cert import CertificateService  # noqa: F401

__all__ = ['CertificateService']
