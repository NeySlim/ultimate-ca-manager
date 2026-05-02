"""PDF generation entry point for UCM executive reports.

Assembles the PDF by delegating to focused submodules:
- report_document: UCMReport FPDF subclass + drawing helpers
- sections_cover:  cover page and table of contents
- sections_cert:   executive summary, risk, cert inventory, expiry, lifecycle
- sections_infra:  compliance, CA hierarchy, audit, recommendations
"""
import io

from .report_document import UCMReport
from .sections_cover import _add_cover_page, _add_toc
from .sections_cert import (
    _add_executive_summary,
    _add_risk_assessment,
    _add_certificate_status,
    _add_expiry_section,
    _add_lifecycle_section,
)
from .sections_infra import (
    _add_compliance_overview,
    _add_ca_section,
    _add_audit_section,
    _add_recommendations,
)

_SECTION_MAP = {
    'executive_summary': _add_executive_summary,
    'risk_assessment': _add_risk_assessment,
    'certificate_status': _add_certificate_status,
    'compliance_overview': _add_compliance_overview,
    'expiry': _add_expiry_section,
    'lifecycle': _add_lifecycle_section,
    'ca_hierarchy': _add_ca_section,
    'audit': _add_audit_section,
    'recommendations': _add_recommendations,
}


def build_pdf(data, sections=None):
    """Render data dict to PDF bytes.  sections limits which sections are included."""
    pdf = UCMReport()
    pdf.alias_nb_pages()

    _add_cover_page(pdf, data)
    _add_toc(pdf, data)
    pdf.add_page()

    selected = sections if sections else list(_SECTION_MAP.keys())
    for section_id in selected:
        builder = _SECTION_MAP.get(section_id)
        if builder:
            builder(pdf, data)

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
