"""UCM PDF reporting package.

PDFReportService is resolved on first access so that importing the templates
or formatters does not pull fpdf.
"""

__all__ = ['PDFReportService']


def __getattr__(name):
    if name == 'PDFReportService':
        from .pdf_report_service import PDFReportService
        return PDFReportService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
