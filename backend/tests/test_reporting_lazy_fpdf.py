"""Listing report schedules and PDF templates must not import fpdf; rendering still works."""
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def _run(code):
    return subprocess.run([sys.executable, '-c', code], cwd=BACKEND, capture_output=True, text=True, timeout=120)


def test_schedulable_reports_leaves_fpdf_unimported():
    r = _run("import sys; from services import report_service as rs; "
             "keys = rs.schedulable_reports(); assert 'pdf_executive' in keys; "
             "print('fpdf' in sys.modules)")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == 'False'


def test_templates_route_helpers_leave_fpdf_unimported():
    r = _run("import sys; from services.reporting.templates import TEMPLATES, ALL_SECTIONS; "
             "assert TEMPLATES and ALL_SECTIONS; print('fpdf' in sys.modules)")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == 'False'


def test_pdf_service_still_importable_lazily():
    r = _run("import sys; import services.reporting as rp; assert 'fpdf' not in sys.modules; "
             "S = rp.PDFReportService; assert hasattr(S, 'generate_executive_report'); "
             "from services.pdf_report_service import PDFReportService as P; assert P is S; "
             "print('fpdf' in sys.modules)")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == 'True'  # first access loads the renderer


def test_pdf_renders(app):
    from services.reporting.pdf_report_service import PDFReportService
    with app.app_context():
        assert PDFReportService.generate_executive_report().startswith(b'%PDF')
