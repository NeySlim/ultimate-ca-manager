"""UCMReport FPDF subclass with UCM branding and low-level drawing primitives."""
import os
import logging

from fpdf import FPDF
from utils.datetime_utils import utc_now
from .formatters import C

logger = logging.getLogger(__name__)


class UCMReport(FPDF):
    """Custom FPDF class with UCM branding."""
    FONT = 'DejaVu'

    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=20)
        self._generated_at = utc_now()
        import matplotlib
        font_dir = os.path.join(os.path.dirname(matplotlib.__file__), 'mpl-data', 'fonts', 'ttf')
        self.add_font('DejaVu', '', os.path.join(font_dir, 'DejaVuSans.ttf'), uni=True)
        self.add_font('DejaVu', 'B', os.path.join(font_dir, 'DejaVuSans-Bold.ttf'), uni=True)
        self.add_font('DejaVu', 'I', os.path.join(font_dir, 'DejaVuSans-Oblique.ttf'), uni=True)

    def header(self):
        if self.page_no() <= 1:
            return
        self.set_fill_color(*C['dark'])
        self.rect(0, 0, 210, 12, style='F')
        self.set_xy(10, 2)
        self.set_font(self.FONT, 'B', 7)
        self.set_text_color(*C['white'])
        self.cell(95, 7, 'UCM  |  PKI Executive Report', align='L')
        self.set_font(self.FONT, '', 7)
        self.cell(95, 7, self._generated_at.strftime('%B %d, %Y  %H:%M UTC'), align='R')
        self.ln(14)

    def footer(self):
        self.set_y(-12)
        self.set_draw_color(*C['slate200'])
        self.line(10, self.get_y(), 200, self.get_y())
        self.set_font(self.FONT, '', 7)
        self.set_text_color(*C['slate500'])
        self.cell(95, 8, 'Confidential', align='L')
        pg = self.page_no()
        self.cell(95, 8, 'Page %d/{nb}' % pg, align='R')

    def section_title(self, title, subtitle=None):
        if self.get_y() > 250:
            self.add_page()
        self.set_font(self.FONT, 'B', 13)
        self.set_text_color(*C['dark'])
        y = self.get_y()
        self.set_fill_color(*C['primary'])
        self.rect(10, y, 2.5, 8, style='F')
        self.set_x(16)
        self.cell(0, 8, title, new_x='LMARGIN', new_y='NEXT')
        if subtitle:
            self.set_x(16)
            self.set_font(self.FONT, '', 8)
            self.set_text_color(*C['slate500'])
            self.cell(0, 5, subtitle, new_x='LMARGIN', new_y='NEXT')
        self.ln(3)

    def stat_card(self, x, y, w, h, value, label, color=None, sub=None):
        color = color or C['primary']
        self.set_fill_color(*C['slate100'])
        self.rect(x, y, w, h, style='F')
        self.set_fill_color(*color)
        self.rect(x, y, 2, h, style='F')
        self.set_xy(x + 4, y + 3)
        self.set_font(self.FONT, 'B', 18)
        self.set_text_color(*color)
        self.cell(w - 6, 8, str(value), align='L', new_x='LMARGIN')
        self.set_xy(x + 4, y + 12)
        self.set_font(self.FONT, '', 7)
        self.set_text_color(*C['slate600'])
        self.cell(w - 6, 5, label, align='L', new_x='LMARGIN')
        if sub:
            self.set_xy(x + 4, y + 17)
            self.set_font(self.FONT, '', 6)
            self.set_text_color(*C['slate400'])
            self.cell(w - 6, 4, sub, align='L', new_x='LMARGIN')

    def h_bar(self, x, y, w_max, value, max_val, color, h=4):
        bw = max((value / max_val) * w_max, 1) if max_val else 1
        self.set_fill_color(*color)
        self.rect(x, y, bw, h, style='F')
        return bw

    def table_header(self, widths, headers):
        self.set_fill_color(*C['dark'])
        self.set_text_color(*C['white'])
        self.set_font(self.FONT, 'B', 7)
        for i, h in enumerate(headers):
            self.cell(widths[i], 7, h, fill=True)
        self.ln()

    def table_row(self, widths, cells, i=0):
        bg = C['slate100'] if i % 2 == 0 else C['white']
        self.set_fill_color(*bg)
        self.set_text_color(*C['dark'])
        self.set_font(self.FONT, '', 7)
        for j, cell in enumerate(cells):
            self.cell(widths[j], 6, str(cell)[:40], fill=True)
        self.ln()


# ---------------------------------------------------------------------------
# Drawing helpers shared across cover/section builders
# ---------------------------------------------------------------------------

def _cover_panel(pdf, x, y, w, h, title, value, color, subtitle):
    """Draw a metric panel on the cover page."""
    pdf.set_fill_color(22, 33, 50)
    pdf.rect(x, y, w, h, style='F')
    pdf.set_fill_color(*color)
    pdf.rect(x, y, w, 3, style='F')

    pdf.set_xy(x + 5, y + 7)
    pdf.set_font(UCMReport.FONT, '', 7)
    pdf.set_text_color(*C['slate400'])
    pdf.cell(w - 10, 4, title)

    pdf.set_xy(x + 5, y + 15)
    pdf.set_font(UCMReport.FONT, 'B', 24)
    pdf.set_text_color(*color)
    pdf.cell(w - 10, 12, str(value), align='L')

    pdf.set_xy(x + 5, y + 32)
    pdf.set_font(UCMReport.FONT, '', 8)
    pdf.set_text_color(*C['slate400'])
    pdf.cell(w - 10, 5, subtitle)


def _risk_gauge(pdf, x, y, w, risk_score):
    """Draw a horizontal risk gauge bar."""
    pdf.set_font(UCMReport.FONT, '', 6)
    pdf.set_text_color(*C['slate500'])
    pdf.set_xy(x, y)
    pdf.cell(20, 4, 'LOW', align='L')
    pdf.cell(w - 40, 4, 'RISK LEVEL', align='C')
    pdf.cell(20, 4, 'HIGH', align='R')

    bar_y = y + 5
    pdf.set_fill_color(30, 41, 59)
    pdf.rect(x, bar_y, w, 5, style='F')

    seg_w = w / 3
    pdf.set_fill_color(*C['success'])
    pdf.rect(x, bar_y, seg_w, 5, style='F')
    pdf.set_fill_color(*C['warning'])
    pdf.rect(x + seg_w, bar_y, seg_w, 5, style='F')
    pdf.set_fill_color(*C['danger'])
    pdf.rect(x + 2 * seg_w, bar_y, seg_w, 5, style='F')

    score_x = x + (risk_score / 100.0) * w
    remaining = w - (risk_score / 100.0) * w
    if remaining > 0.5:
        pdf.set_fill_color(22, 33, 50)
        pdf.set_draw_color(22, 33, 50)
        pdf.rect(score_x, bar_y, remaining, 5, style='FD')

    pdf.set_fill_color(*C['white'])
    indicator_x = max(x + 1, min(score_x, x + w - 1))
    pdf.rect(indicator_x - 1, bar_y - 1.5, 2, 2, style='F')

    pdf.set_xy(indicator_x - 8, bar_y + 6)
    pdf.set_font(UCMReport.FONT, 'B', 7)
    pdf.set_text_color(*C['white'])
    pdf.cell(16, 4, '%d/100' % risk_score, align='C')
