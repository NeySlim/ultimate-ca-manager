"""Main PDFReportService class — orchestrates data collection and PDF generation."""
import logging

from .formatters import collect_report_data
from .pdf_generator import build_pdf
from .templates import ALL_SECTIONS, TEMPLATES

logger = logging.getLogger(__name__)


class PDFReportService:
    """Generate executive PDF reports with charts and stats."""

    ALL_SECTIONS = ALL_SECTIONS
    TEMPLATES = TEMPLATES

    @classmethod
    def generate_executive_report(cls, sections=None):
        """Generate PDF report. Optionally limit to specific sections. Returns bytes."""
        try:
            data = collect_report_data()
            return build_pdf(data, sections=sections)
        except Exception as e:
            logger.error('Failed to generate PDF report: %s', e, exc_info=True)
            raise
