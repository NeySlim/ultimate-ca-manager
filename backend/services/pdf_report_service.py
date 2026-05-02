"""Backward-compatibility shim for services.pdf_report_service.

The implementation has moved to services.reporting.
"""
from services.reporting.pdf_report_service import PDFReportService

__all__ = ['PDFReportService']
