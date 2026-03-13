"""
PDF Executive Report Service - UCM
Generates polished PDF reports with charts for management/executive audiences.
Uses fpdf2 for PDF generation.
"""
import io
import os
import logging
from datetime import datetime, timedelta
from collections import Counter

from fpdf import FPDF
from models import db, Certificate, CA, AuditLog, SystemConfig
from services.compliance_service import calculate_compliance_score

logger = logging.getLogger(__name__)

# UCM brand colors (RGB tuples)
C = {
    'primary': (59, 130, 246),
    'primary_dark': (37, 99, 235),
    'success': (34, 197, 94),
    'warning': (234, 179, 8),
    'danger': (239, 68, 68),
    'dark': (15, 23, 42),
    'slate700': (51, 65, 85),
    'slate600': (71, 85, 105),
    'slate500': (100, 116, 139),
    'slate400': (148, 163, 184),
    'slate200': (226, 232, 240),
    'slate100': (241, 245, 249),
    'white': (255, 255, 255),
    'grade_a': (34, 197, 94),
    'grade_b': (59, 130, 246),
    'grade_c': (234, 179, 8),
    'grade_d': (249, 115, 22),
    'grade_f': (239, 68, 68),
    'accent_teal': (20, 184, 166),
}


class UCMReport(FPDF):
    """Custom FPDF class with UCM branding."""
    FONT = 'DejaVu'

    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=20)
        self._generated_at = datetime.utcnow()
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

    # -- drawing helpers -----------------------------------------------

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


class PDFReportService:
    """Generate executive PDF reports with charts and stats."""

    @classmethod
    def generate_executive_report(cls):
        """Generate the full executive PDF report. Returns bytes."""
        try:
            data = cls._collect_all_data()
            pdf = cls._build_pdf(data)
            return pdf
        except Exception as e:
            logger.error('Failed to generate PDF report: %s', e, exc_info=True)
            raise

    # -- data collection -----------------------------------------------

    @classmethod
    def _collect_all_data(cls):
        now = datetime.utcnow()

        all_certs = Certificate.query.all()
        active, expired, expiring_30, expiring_7, revoked = [], [], [], [], []
        status_counts = Counter()
        algo_counts = Counter()
        source_counts = Counter()
        lifetime_days = []
        compliance_scores = []
        compliance_breakdowns = []
        grade_counts = Counter()

        for cert in all_certs:
            status = cls._cert_status(cert, now)
            status_counts[status] += 1
            if cert.key_algo:
                algo_counts[cert.key_algo.upper()] += 1
            source_counts[cert.source or 'manual'] += 1

            if cert.valid_from and cert.valid_to:
                lt = (cert.valid_to - cert.valid_from).days
                if lt > 0:
                    lifetime_days.append(lt)

            if status == 'valid':
                active.append(cert)
            elif status == 'expired':
                expired.append(cert)
            elif status == 'revoked':
                revoked.append(cert)

            if cert.valid_to and not cert.revoked:
                days_left = (cert.valid_to - now).days
                if 0 < days_left <= 30:
                    expiring_30.append(cert)
                if 0 < days_left <= 7:
                    expiring_7.append(cert)

            try:
                cd = cert.to_dict() if hasattr(cert, 'to_dict') else cert
                sd = calculate_compliance_score(cd)
                compliance_scores.append(sd['score'])
                compliance_breakdowns.append(sd.get('breakdown', {}))
                grade_counts[sd['grade']] += 1
            except Exception:
                grade_counts['F'] += 1
                compliance_scores.append(0)

        # CAs
        all_cas = CA.query.all()
        root_cas = [ca for ca in all_cas if not ca.caref]
        intermediate_cas = [ca for ca in all_cas if ca.caref]

        # Average compliance per category
        category_scores = {}
        for bd in compliance_breakdowns:
            for cat, info in bd.items():
                if isinstance(info, dict) and 'score' in info and 'max' in info:
                    if cat not in category_scores:
                        category_scores[cat] = {'total': 0, 'max': 0, 'count': 0}
                    category_scores[cat]['total'] += info['score']
                    category_scores[cat]['max'] += info['max']
                    category_scores[cat]['count'] += 1

        avg_score = round(sum(compliance_scores) / len(compliance_scores)) if compliance_scores else 0
        avg_grade = cls._score_to_grade(avg_score)

        # Audit (30 days)
        thirty_days_ago = now - timedelta(days=30)
        recent_logs = AuditLog.query.filter(AuditLog.timestamp >= thirty_days_ago).all()
        action_counts = Counter()
        daily_activity = Counter()
        failed_logins = 0
        unique_users = set()
        for log in recent_logs:
            action_counts[log.action] += 1
            if log.timestamp:
                daily_activity[log.timestamp.strftime('%Y-%m-%d')] += 1
            if log.action == 'login_failed':
                failed_logins += 1
            if log.username:
                unique_users.add(log.username)

        # Discovery scan info
        last_scan = None
        try:
            from models import DiscoveryHistory
            scan = DiscoveryHistory.query.order_by(DiscoveryHistory.id.desc()).first()
            if scan:
                last_scan = {
                    'date': scan.started_at if hasattr(scan, 'started_at') else None,
                    'hosts': getattr(scan, 'hosts_scanned', None),
                    'certs_found': getattr(scan, 'certificates_found', None),
                }
        except Exception:
            pass

        # Risk assessment
        risk_score = 0
        risk_items = []
        if len(expiring_7) > 0:
            risk_score += 30
            risk_items.append(('CRITICAL', '%d cert(s) expire within 7 days' % len(expiring_7)))
        if len(expiring_30) > 3:
            risk_score += 15
            risk_items.append(('HIGH', '%d cert(s) expire within 30 days' % len(expiring_30)))
        elif len(expiring_30) > 0:
            risk_score += 5
            risk_items.append(('MEDIUM', '%d cert(s) expire within 30 days' % len(expiring_30)))
        if len(expired) > 0:
            risk_score += 20
            risk_items.append(('HIGH', '%d expired cert(s) still in inventory' % len(expired)))
        if avg_score < 50:
            risk_score += 25
            risk_items.append(('HIGH', 'Low compliance score (%d/100)' % avg_score))
        elif avg_score < 70:
            risk_score += 10
            risk_items.append(('MEDIUM', 'Moderate compliance (%d/100)' % avg_score))
        if failed_logins > 20:
            risk_score += 15
            risk_items.append(('HIGH', '%d failed logins in 30 days' % failed_logins))
        elif failed_logins > 5:
            risk_score += 5
            risk_items.append(('LOW', '%d failed logins in 30 days' % failed_logins))

        if risk_score >= 40:
            risk_level = 'HIGH'
        elif risk_score >= 15:
            risk_level = 'MEDIUM'
        else:
            risk_level = 'LOW'

        # Version
        version = 'N/A'
        try:
            for p in ['/opt/ucm/VERSION', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'VERSION')]:
                if os.path.exists(p):
                    with open(p, 'r') as f:
                        version = f.read().strip()
                    break
        except Exception:
            pass

        return {
            'generated_at': now,
            'version': version,
            'total_certs': len(all_certs),
            'active_certs': len(active),
            'expired_certs': len(expired),
            'expiring_30': expiring_30,
            'expiring_7': expiring_7,
            'revoked_certs': len(revoked),
            'status_counts': dict(status_counts),
            'algo_counts': dict(algo_counts),
            'source_counts': dict(source_counts),
            'lifetime_days': lifetime_days,
            'total_cas': len(all_cas),
            'root_cas': len(root_cas),
            'intermediate_cas': len(intermediate_cas),
            'ca_list': all_cas,
            'avg_score': avg_score,
            'avg_grade': avg_grade,
            'grade_counts': dict(grade_counts),
            'category_scores': category_scores,
            'action_counts': dict(action_counts),
            'daily_activity': dict(daily_activity),
            'failed_logins': failed_logins,
            'unique_users': len(unique_users),
            'total_audit_events': len(recent_logs),
            'all_certs': all_certs,
            'risk_level': risk_level,
            'risk_score': risk_score,
            'risk_items': risk_items,
            'last_scan': last_scan,
        }

    # -- PDF builder ---------------------------------------------------

    @classmethod
    def _build_pdf(cls, data):
        pdf = UCMReport()
        pdf.alias_nb_pages()

        cls._add_cover_page(pdf, data)
        cls._add_toc(pdf, data)
        pdf.add_page()
        cls._add_executive_summary(pdf, data)
        cls._add_risk_assessment(pdf, data)
        cls._add_certificate_status(pdf, data)
        cls._add_compliance_overview(pdf, data)
        cls._add_expiry_section(pdf, data)
        cls._add_lifecycle_section(pdf, data)
        cls._add_ca_section(pdf, data)
        cls._add_audit_section(pdf, data)
        cls._add_recommendations(pdf, data)

        buf = io.BytesIO()
        pdf.output(buf)
        return buf.getvalue()

    # -- cover page ----------------------------------------------------

    @classmethod
    def _add_cover_page(cls, pdf, data):
        pdf.add_page()
        pdf.set_auto_page_break(auto=False)

        # Full-page dark background
        pdf.set_fill_color(*C['dark'])
        pdf.rect(0, 0, 210, 297, style='F')

        # Accent stripe at top
        pdf.set_fill_color(*C['primary'])
        pdf.rect(0, 0, 210, 5, style='F')

        # UCM wordmark
        pdf.set_xy(10, 14)
        pdf.set_font(UCMReport.FONT, 'B', 9)
        pdf.set_text_color(*C['primary'])
        pdf.cell(0, 6, 'ULTIMATE CA MANAGER')

        # Version badge
        pdf.set_xy(160, 14)
        pdf.set_font(UCMReport.FONT, '', 8)
        pdf.set_text_color(*C['slate400'])
        pdf.cell(40, 6, 'v' + data['version'], align='R')

        # Main title
        pdf.set_xy(10, 38)
        pdf.set_font(UCMReport.FONT, 'B', 36)
        pdf.set_text_color(*C['white'])
        pdf.cell(0, 16, 'PKI Executive', new_x='LMARGIN', new_y='NEXT')
        pdf.set_x(10)
        pdf.cell(0, 16, 'Report', new_x='LMARGIN', new_y='NEXT')

        # Date
        pdf.set_xy(10, 78)
        pdf.set_font(UCMReport.FONT, '', 11)
        pdf.set_text_color(*C['slate400'])
        pdf.cell(0, 7, data['generated_at'].strftime('%B %d, %Y'))

        # Divider line
        pdf.set_draw_color(*C['primary'])
        pdf.set_line_width(0.6)
        pdf.line(10, 92, 200, 92)
        pdf.set_line_width(0.2)

        # -- 3 large metric panels --
        risk = data['risk_level']
        risk_color = C['success'] if risk == 'LOW' else C['warning'] if risk == 'MEDIUM' else C['danger']
        grade_color = C.get('grade_' + data['avg_grade'][0].lower(), C['slate500'])

        panel_w = 58
        panel_h = 46
        panel_gap = 8
        panel_y = 100

        # Panel 1: Risk Assessment
        x1 = 10
        cls._cover_panel(pdf, x1, panel_y, panel_w, panel_h,
                         'RISK ASSESSMENT', risk, risk_color,
                         'Score: %d / 100' % data['risk_score'])

        # Panel 2: Compliance Grade
        x2 = x1 + panel_w + panel_gap
        cls._cover_panel(pdf, x2, panel_y, panel_w, panel_h,
                         'COMPLIANCE GRADE',
                         '%s' % data['avg_grade'], grade_color,
                         '%d / 100 average' % data['avg_score'])

        # Panel 3: Certificates
        x3 = x2 + panel_w + panel_gap
        cls._cover_panel(pdf, x3, panel_y, panel_w, panel_h,
                         'CERTIFICATES', str(data['total_certs']), C['primary'],
                         '%d active, %d expiring' % (data['active_certs'], len(data['expiring_30'])))

        # -- Risk gauge bar --
        gauge_y = panel_y + panel_h + 10
        cls._risk_gauge(pdf, 10, gauge_y, 190, data['risk_score'])

        # -- Key Findings box --
        findings_y = gauge_y + 18
        pdf.set_fill_color(22, 33, 50)
        pdf.rect(10, findings_y, 190, 36, style='F')
        pdf.set_fill_color(*C['primary'])
        pdf.rect(10, findings_y, 3, 36, style='F')

        pdf.set_xy(18, findings_y + 3)
        pdf.set_font(UCMReport.FONT, 'B', 9)
        pdf.set_text_color(*C['white'])
        pdf.cell(0, 5, 'KEY FINDINGS')

        findings = []
        if len(data['expiring_30']) > 0:
            findings.append('%d certificate(s) expiring within 30 days' % len(data['expiring_30']))
        if data['expired_certs'] > 0:
            findings.append('%d expired certificate(s) in inventory' % data['expired_certs'])
        if data['revoked_certs'] > 0:
            findings.append('%d revoked certificate(s)' % data['revoked_certs'])
        manual_count = data['source_counts'].get('manual', 0)
        acme_count = data['source_counts'].get('acme', 0)
        if data['total_certs'] > 0:
            auto_pct = round(acme_count / data['total_certs'] * 100)
            findings.append('%d%% automation rate (%d ACME, %d manual)' % (auto_pct, acme_count, manual_count))
        if not findings:
            findings.append('No critical issues detected')

        pdf.set_font(UCMReport.FONT, '', 8)
        pdf.set_text_color(*C['slate200'])
        for i, finding in enumerate(findings[:4]):
            pdf.set_xy(18, findings_y + 11 + i * 6)
            pdf.set_fill_color(*C['slate400'])
            pdf.rect(18, findings_y + 12.5 + i * 6, 2, 2, style='F')
            pdf.set_x(23)
            pdf.cell(0, 5, finding)

        # -- Bottom stat cards (5 metrics) --
        stats_y = findings_y + 44
        cw = 35
        gap = 3.75
        metrics = [
            (str(data['active_certs']), 'Active', C['success']),
            (str(len(data['expiring_30'])), 'Expiring', C['warning']),
            (str(data['expired_certs']), 'Expired', C['danger']),
            (str(data['revoked_certs']), 'Revoked', C['slate500']),
            (str(data['total_cas']), 'CAs', C['primary']),
        ]
        for i, (val, label, color) in enumerate(metrics):
            x = 10 + i * (cw + gap)
            pdf.set_fill_color(22, 33, 50)
            pdf.rect(x, stats_y, cw, 20, style='F')
            pdf.set_fill_color(*color)
            pdf.rect(x, stats_y, 2, 20, style='F')
            pdf.set_xy(x + 4, stats_y + 2)
            pdf.set_font(UCMReport.FONT, 'B', 14)
            pdf.set_text_color(*C['white'])
            pdf.cell(cw - 6, 7, val, align='L')
            pdf.set_xy(x + 4, stats_y + 10)
            pdf.set_font(UCMReport.FONT, '', 7)
            pdf.set_text_color(*C['slate400'])
            pdf.cell(cw - 6, 5, label, align='L')

        # -- Footer area --
        pdf.set_draw_color(*C['slate700'])
        pdf.line(10, 275, 200, 275)
        pdf.set_xy(10, 276)
        pdf.set_font(UCMReport.FONT, 'I', 7)
        pdf.set_text_color(*C['slate500'])
        pdf.cell(95, 5, 'Confidential - Authorized personnel only')
        pdf.cell(95, 5, data['generated_at'].strftime('%B %d, %Y  %H:%M UTC'), align='R')

        pdf.set_auto_page_break(auto=True, margin=20)

    @classmethod
    def _cover_panel(cls, pdf, x, y, w, h, title, value, color, subtitle):
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

    @classmethod
    def _risk_gauge(cls, pdf, x, y, w, risk_score):
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

        # Green -> Yellow -> Red gradient approximation (3 segments)
        seg_w = w / 3
        pdf.set_fill_color(*C['success'])
        pdf.rect(x, bar_y, seg_w, 5, style='F')
        pdf.set_fill_color(*C['warning'])
        pdf.rect(x + seg_w, bar_y, seg_w, 5, style='F')
        pdf.set_fill_color(*C['danger'])
        pdf.rect(x + 2 * seg_w, bar_y, seg_w, 5, style='F')

        # Dark overlay for "unused" portion (right side beyond score)
        score_x = x + (risk_score / 100.0) * w
        remaining = w - (risk_score / 100.0) * w
        if remaining > 0.5:
            pdf.set_fill_color(22, 33, 50)
            pdf.set_draw_color(22, 33, 50)
            pdf.rect(score_x, bar_y, remaining, 5, style='FD')

        # Score indicator triangle (small)
        pdf.set_fill_color(*C['white'])
        indicator_x = max(x + 1, min(score_x, x + w - 1))
        pdf.rect(indicator_x - 1, bar_y - 1.5, 2, 2, style='F')

        # Score label
        pdf.set_xy(indicator_x - 8, bar_y + 6)
        pdf.set_font(UCMReport.FONT, 'B', 7)
        pdf.set_text_color(*C['white'])
        pdf.cell(16, 4, '%d/100' % risk_score, align='C')

    # -- table of contents ---------------------------------------------

    @classmethod
    def _add_toc(cls, pdf, data):
        pdf.add_page()
        pdf.set_font(UCMReport.FONT, 'B', 18)
        pdf.set_text_color(*C['dark'])
        pdf.cell(0, 12, 'Table of Contents', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(4)

        sections = [
            ('1', 'Executive Summary', 'High-level overview and key findings'),
            ('2', 'Risk Assessment', 'Detailed risk analysis and severity breakdown'),
            ('3', 'Certificate Inventory', 'Status distribution, algorithms, and sources'),
            ('4', 'Compliance Overview', 'Grades, scores, and per-category breakdown'),
            ('5', 'Expiring Certificates', 'Certificates requiring immediate attention'),
            ('6', 'Certificate Lifecycle', 'Age distribution and lifetime analysis'),
            ('7', 'CA Infrastructure', 'Certificate Authority hierarchy'),
            ('8', 'Security & Audit', 'Login activity and top actions (30 days)'),
            ('9', 'Recommendations', 'Actionable improvements for PKI posture'),
        ]

        for num, title, desc in sections:
            y = pdf.get_y()
            pdf.set_fill_color(*C['primary'])
            pdf.rect(10, y + 1, 2, 10, style='F')
            pdf.set_xy(16, y)
            pdf.set_font(UCMReport.FONT, 'B', 10)
            pdf.set_text_color(*C['dark'])
            pdf.cell(0, 6, '%s.  %s' % (num, title), new_x='LMARGIN', new_y='NEXT')
            pdf.set_x(16)
            pdf.set_font(UCMReport.FONT, '', 8)
            pdf.set_text_color(*C['slate500'])
            pdf.cell(0, 5, desc, new_x='LMARGIN', new_y='NEXT')
            pdf.ln(3)

    # -- 1. executive summary ------------------------------------------

    @classmethod
    def _add_executive_summary(cls, pdf, data):
        pdf.section_title('1. Executive Summary')

        pdf.set_font(UCMReport.FONT, '', 9)
        pdf.set_text_color(*C['dark'])

        now = data['generated_at']
        summary = (
            'This report provides a comprehensive overview of your PKI infrastructure managed by '
            'Ultimate Certificate Manager. As of %s, the system manages '
            '%d certificates across %d Certificate Authorities.'
        ) % (now.strftime('%B %d, %Y'), data['total_certs'], data['total_cas'])
        pdf.multi_cell(0, 5, summary)
        pdf.ln(3)

        # Key metrics row
        y = pdf.get_y()
        cw = 43
        gap = 5
        grade_color = C.get('grade_' + data['avg_grade'][0].lower(), C['slate500'])
        risk_color = C['success'] if data['risk_level'] == 'LOW' else C['warning'] if data['risk_level'] == 'MEDIUM' else C['danger']
        pdf.stat_card(10, y, cw, 26, data['total_certs'], 'Total Certificates', C['primary'],
                      '%d active' % data['active_certs'])
        pdf.stat_card(10 + cw + gap, y, cw, 26, data['avg_grade'], 'Compliance Grade',
                      grade_color, '%d/100' % data['avg_score'])
        pdf.stat_card(10 + 2 * (cw + gap), y, cw, 26, data['total_cas'], 'CAs', C['primary'],
                      '%d root, %d intermediate' % (data['root_cas'], data['intermediate_cas']))
        pdf.stat_card(10 + 3 * (cw + gap), y, cw, 26, data['risk_level'], 'Risk Level', risk_color)
        pdf.set_y(y + 32)

        # Key findings
        pdf.set_font(UCMReport.FONT, 'B', 10)
        pdf.set_text_color(*C['dark'])
        pdf.cell(0, 6, 'Key Findings', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(1)

        findings = []
        if len(data['expiring_7']) > 0:
            findings.append(('%d certificate(s) expiring within 7 days' % len(data['expiring_7']), C['danger']))
        if len(data['expiring_30']) > 0:
            findings.append(('%d certificate(s) expiring within 30 days' % len(data['expiring_30']), C['warning']))
        if data['expired_certs'] > 0:
            findings.append(('%d expired certificate(s) in inventory' % data['expired_certs'], C['danger']))
        if data['revoked_certs'] > 0:
            findings.append(('%d revoked certificate(s)' % data['revoked_certs'], C['slate500']))
        if data['avg_score'] >= 80:
            findings.append(('Strong compliance posture (%d/100)' % data['avg_score'], C['success']))
        elif data['avg_score'] >= 60:
            findings.append(('Moderate compliance (%d/100)' % data['avg_score'], C['warning']))
        else:
            findings.append(('Low compliance score (%d/100)' % data['avg_score'], C['danger']))

        for text, color in findings:
            y = pdf.get_y()
            pdf.set_fill_color(*color)
            pdf.rect(14, y + 1.5, 2, 2, style='F')
            pdf.set_x(20)
            pdf.set_font(UCMReport.FONT, '', 9)
            pdf.set_text_color(*C['dark'])
            pdf.cell(0, 5, text, new_x='LMARGIN', new_y='NEXT')

        pdf.ln(6)

    # -- 2. risk assessment --------------------------------------------

    @classmethod
    def _add_risk_assessment(cls, pdf, data):
        pdf.section_title('2. Risk Assessment', 'Identified risks and their severity levels')

        risk = data['risk_level']
        risk_color = C['success'] if risk == 'LOW' else C['warning'] if risk == 'MEDIUM' else C['danger']

        # Risk level box
        y = pdf.get_y()
        pdf.set_fill_color(*risk_color)
        pdf.rect(10, y, 50, 16, style='F')
        pdf.set_xy(10, y + 2)
        pdf.set_font(UCMReport.FONT, 'B', 14)
        pdf.set_text_color(*C['white'])
        pdf.cell(50, 12, '  %s RISK' % risk, align='L', new_x='LMARGIN')

        pdf.set_xy(65, y + 2)
        pdf.set_font(UCMReport.FONT, '', 9)
        pdf.set_text_color(*C['dark'])
        pdf.multi_cell(130, 5,
            'Risk score: %d/100. Based on certificate expiry status, compliance posture, and security events.' % data['risk_score']
        )
        pdf.set_y(y + 22)

        if data['risk_items']:
            pdf.set_font(UCMReport.FONT, 'B', 9)
            pdf.set_text_color(*C['dark'])
            pdf.cell(0, 6, 'Risk Items:', new_x='LMARGIN', new_y='NEXT')

            widths = [25, 165]
            pdf.table_header(widths, ['Severity', 'Description'])
            for i, (severity, desc) in enumerate(data['risk_items']):
                sc = C['danger'] if severity == 'CRITICAL' else C['warning'] if severity in ('HIGH', 'MEDIUM') else C['success']
                bg = C['slate100'] if i % 2 == 0 else C['white']
                pdf.set_fill_color(*bg)
                pdf.set_text_color(*sc)
                pdf.set_font(UCMReport.FONT, 'B', 7)
                pdf.cell(widths[0], 6, severity, fill=True)
                pdf.set_text_color(*C['dark'])
                pdf.set_font(UCMReport.FONT, '', 7)
                pdf.cell(widths[1], 6, desc, fill=True)
                pdf.ln()
        else:
            pdf.set_font(UCMReport.FONT, '', 9)
            pdf.set_text_color(*C['success'])
            pdf.cell(0, 6, '+ No significant risks identified.', new_x='LMARGIN', new_y='NEXT')

        pdf.ln(6)

    # -- 3. certificate inventory --------------------------------------

    @classmethod
    def _add_certificate_status(cls, pdf, data):
        if pdf.get_y() > 200:
            pdf.add_page()
        pdf.section_title('3. Certificate Inventory', '%d certificates managed' % data['total_certs'])

        total = max(data['total_certs'], 1)

        # Status stacked bar
        statuses = [
            ('Valid', data['active_certs'], C['success']),
            ('Expiring', len(data['expiring_30']), C['warning']),
            ('Expired', data['expired_certs'], C['danger']),
            ('Revoked', data['revoked_certs'], C['slate500']),
        ]
        y = pdf.get_y()
        x = 10
        for label, count, color in statuses:
            if count > 0:
                w = max((count / total) * 190, 3)
                pdf.set_fill_color(*color)
                pdf.rect(x, y, w, 10, style='F')
                if w > 18:
                    pdf.set_xy(x, y + 1)
                    pdf.set_font(UCMReport.FONT, 'B', 7)
                    pdf.set_text_color(*C['white'])
                    pdf.cell(w, 4, str(count), align='C', new_x='LMARGIN')
                    pdf.set_xy(x, y + 5)
                    pdf.set_font(UCMReport.FONT, '', 5.5)
                    pdf.cell(w, 4, label, align='C', new_x='LMARGIN')
                x += w
        pdf.set_y(y + 14)

        # Legend
        pdf.set_font(UCMReport.FONT, '', 7)
        for label, count, color in statuses:
            pdf.set_fill_color(*color)
            pdf.rect(pdf.get_x(), pdf.get_y() + 1, 3, 3, style='F')
            pdf.set_x(pdf.get_x() + 5)
            pdf.set_text_color(*C['dark'])
            pct = round(count / total * 100) if total else 0
            pdf.cell(40, 5, '%s: %d (%d%%)' % (label, count, pct))
        pdf.ln(8)

        # Two-column: Algorithms | Sources
        y_start = pdf.get_y()

        # Left: Key Algorithms
        pdf.set_font(UCMReport.FONT, 'B', 9)
        pdf.set_text_color(*C['dark'])
        pdf.cell(90, 6, 'Key Algorithms', new_x='LMARGIN', new_y='NEXT')
        max_algo = max(data['algo_counts'].values()) if data['algo_counts'] else 1
        for algo, count in sorted(data['algo_counts'].items(), key=lambda x: -x[1]):
            y = pdf.get_y()
            pdf.set_font(UCMReport.FONT, '', 8)
            pdf.set_text_color(*C['dark'])
            pdf.cell(30, 5, algo)
            bw = pdf.h_bar(pdf.get_x(), y + 0.5, 40, count, max_algo, C['primary'])
            pdf.set_x(pdf.get_x() + bw + 3)
            pdf.set_font(UCMReport.FONT, '', 7)
            pdf.set_text_color(*C['slate500'])
            pct = round(count / total * 100)
            pdf.cell(0, 5, '%d (%d%%)' % (count, pct), new_x='LMARGIN', new_y='NEXT')
        y_after_algo = pdf.get_y()

        # Right: Sources
        pdf.set_y(y_start)
        pdf.set_x(110)
        pdf.set_font(UCMReport.FONT, 'B', 9)
        pdf.set_text_color(*C['dark'])
        pdf.cell(90, 6, 'Certificate Sources')
        pdf.ln()
        max_src = max(data['source_counts'].values()) if data['source_counts'] else 1
        for src, count in sorted(data['source_counts'].items(), key=lambda x: -x[1]):
            y = pdf.get_y()
            pdf.set_x(110)
            pdf.set_font(UCMReport.FONT, '', 8)
            pdf.set_text_color(*C['dark'])
            label = src.replace('_', ' ').title()
            pdf.cell(25, 5, label)
            bw = pdf.h_bar(pdf.get_x(), y + 0.5, 35, count, max_src, C['accent_teal'])
            pdf.set_x(pdf.get_x() + bw + 3)
            pdf.set_font(UCMReport.FONT, '', 7)
            pdf.set_text_color(*C['slate500'])
            pdf.cell(0, 5, str(count), new_x='LMARGIN', new_y='NEXT')

        pdf.set_y(max(y_after_algo, pdf.get_y()) + 6)

    # -- 4. compliance overview ----------------------------------------

    @classmethod
    def _add_compliance_overview(cls, pdf, data):
        if pdf.get_y() > 220:
            pdf.add_page()
        pdf.section_title('4. Compliance Overview', 'Certificate quality scoring based on cryptographic best practices')

        y = pdf.get_y()
        grade_color = C.get('grade_' + data['avg_grade'][0].lower(), C['slate500'])
        pdf.set_fill_color(*grade_color)
        pdf.rect(10, y, 24, 24, style='F')
        pdf.set_xy(10, y + 3)
        pdf.set_font(UCMReport.FONT, 'B', 18)
        pdf.set_text_color(*C['white'])
        pdf.cell(24, 10, data['avg_grade'], align='C', new_x='LMARGIN')
        pdf.set_xy(10, y + 14)
        pdf.set_font(UCMReport.FONT, '', 7)
        pdf.cell(24, 5, '%d/100' % data['avg_score'], align='C', new_x='LMARGIN')

        pdf.set_xy(40, y + 2)
        pdf.set_font(UCMReport.FONT, 'B', 11)
        pdf.set_text_color(*C['dark'])
        pdf.cell(0, 6, 'Overall Compliance Grade: %s' % data['avg_grade'])
        pdf.set_xy(40, y + 10)
        pdf.set_font(UCMReport.FONT, '', 8)
        pdf.set_text_color(*C['slate500'])
        pdf.cell(0, 5, 'Average score %d/100 across %d certificates' % (data['avg_score'], data['total_certs']))

        pdf.set_y(y + 30)

        # Grade distribution
        pdf.set_font(UCMReport.FONT, 'B', 9)
        pdf.set_text_color(*C['dark'])
        pdf.cell(0, 6, 'Grade Distribution', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(1)

        max_gc = max(data['grade_counts'].values()) if data['grade_counts'] else 1
        for grade in ['A+', 'A', 'B', 'C', 'D', 'F']:
            count = data['grade_counts'].get(grade, 0)
            if count == 0 and grade == 'A+':
                continue
            color = C.get('grade_' + grade[0].lower(), C['slate500'])
            y = pdf.get_y()
            pdf.set_font(UCMReport.FONT, 'B', 8)
            pdf.set_text_color(*color)
            pdf.cell(10, 5, grade)
            bw = pdf.h_bar(pdf.get_x(), y + 0.5, 100, count, max_gc, color)
            pdf.set_x(pdf.get_x() + bw + 3)
            pdf.set_font(UCMReport.FONT, '', 7)
            pdf.set_text_color(*C['dark'])
            pct = round(count / max(data['total_certs'], 1) * 100)
            pdf.cell(0, 5, '%d (%d%%)' % (count, pct), new_x='LMARGIN', new_y='NEXT')

        pdf.ln(3)

        # Per-category scores
        if data['category_scores']:
            pdf.set_font(UCMReport.FONT, 'B', 9)
            pdf.set_text_color(*C['dark'])
            pdf.cell(0, 6, 'Score Breakdown by Category', new_x='LMARGIN', new_y='NEXT')
            pdf.ln(1)

            cat_labels = {
                'key_strength': 'Key Strength',
                'signature': 'Signature Algorithm',
                'validity': 'Validity Status',
                'san': 'SAN Presence',
                'lifetime': 'Certificate Lifetime',
            }
            for cat, info in data['category_scores'].items():
                avg = round(info['total'] / info['count']) if info['count'] else 0
                max_pts = round(info['max'] / info['count']) if info['count'] else 0
                pct = round(avg / max_pts * 100) if max_pts else 0
                label = cat_labels.get(cat, cat.replace('_', ' ').title())

                y = pdf.get_y()
                pdf.set_font(UCMReport.FONT, '', 8)
                pdf.set_text_color(*C['dark'])
                pdf.cell(40, 5, label)

                bar_x = pdf.get_x()
                pdf.set_fill_color(*C['slate200'])
                pdf.rect(bar_x, y + 0.5, 80, 4, style='F')
                color = C['success'] if pct >= 80 else C['warning'] if pct >= 50 else C['danger']
                fill_w = max(pct * 0.8, 0.5)
                pdf.set_fill_color(*color)
                pdf.rect(bar_x, y + 0.5, fill_w, 4, style='F')

                pdf.set_x(bar_x + 84)
                pdf.set_font(UCMReport.FONT, '', 7)
                pdf.set_text_color(*C['slate600'])
                pdf.cell(0, 5, '%d/%d pts (%d%%)' % (avg, max_pts, pct), new_x='LMARGIN', new_y='NEXT')

        pdf.ln(6)

    # -- 5. expiring certificates --------------------------------------

    @classmethod
    def _add_expiry_section(cls, pdf, data):
        if not data['expiring_30']:
            return
        if pdf.get_y() > 210:
            pdf.add_page()

        pdf.section_title('5. Expiring Certificates',
                          '%d certificate(s) expiring within 30 days' % len(data['expiring_30']))

        now = datetime.utcnow()
        widths = [65, 45, 20, 30, 30]
        headers = ['Certificate', 'Issuer', 'Days', 'Expires', 'Algorithm']
        pdf.table_header(widths, headers)

        for i, cert in enumerate(sorted(data['expiring_30'], key=lambda c: c.valid_to or now)[:20]):
            days_left = (cert.valid_to - now).days if cert.valid_to else 0
            name = (cert.descr or cert.subject_cn or 'N/A')[:30]
            issuer = (cert.issuer or 'N/A')[:22]
            expires = cert.valid_to.strftime('%Y-%m-%d') if cert.valid_to else 'N/A'
            algo = (cert.key_algo or 'N/A')[:15]

            bg = C['slate100'] if i % 2 == 0 else C['white']
            pdf.set_fill_color(*bg)
            pdf.set_font(UCMReport.FONT, '', 7)

            if days_left <= 7:
                pdf.set_text_color(*C['danger'])
            elif days_left <= 14:
                pdf.set_text_color(*C['warning'])
            else:
                pdf.set_text_color(*C['dark'])

            pdf.cell(widths[0], 6, name, fill=True)
            pdf.set_text_color(*C['dark'])
            pdf.cell(widths[1], 6, issuer, fill=True)

            if days_left <= 7:
                pdf.set_text_color(*C['danger'])
                pdf.set_font(UCMReport.FONT, 'B', 7)
            pdf.cell(widths[2], 6, '%dd' % days_left, fill=True)
            pdf.set_text_color(*C['dark'])
            pdf.set_font(UCMReport.FONT, '', 7)
            pdf.cell(widths[3], 6, expires, fill=True)
            pdf.cell(widths[4], 6, algo, fill=True)
            pdf.ln()

        if len(data['expiring_30']) > 20:
            pdf.set_font(UCMReport.FONT, 'I', 7)
            pdf.set_text_color(*C['slate500'])
            pdf.cell(0, 5, '  ... and %d more' % (len(data['expiring_30']) - 20), new_x='LMARGIN', new_y='NEXT')

        pdf.ln(6)

    # -- 6. certificate lifecycle --------------------------------------

    @classmethod
    def _add_lifecycle_section(cls, pdf, data):
        if not data['lifetime_days']:
            return
        if pdf.get_y() > 220:
            pdf.add_page()

        pdf.section_title('6. Certificate Lifecycle', 'Validity period distribution and age analysis')

        days = data['lifetime_days']
        avg_days = round(sum(days) / len(days))
        min_days = min(days)
        max_days = max(days)

        y = pdf.get_y()
        cw = 43
        gap = 5
        pdf.stat_card(10, y, cw, 22, '%dd' % avg_days, 'Average Lifetime', C['primary'])
        pdf.stat_card(10 + cw + gap, y, cw, 22, '%dd' % min_days, 'Shortest', C['accent_teal'])
        pdf.stat_card(10 + 2 * (cw + gap), y, cw, 22, '%dd' % max_days, 'Longest', C['warning'])
        pdf.stat_card(10 + 3 * (cw + gap), y, cw, 22, len(days), 'Total', C['slate600'])
        pdf.set_y(y + 28)

        # Distribution
        pdf.set_font(UCMReport.FONT, 'B', 9)
        pdf.set_text_color(*C['dark'])
        pdf.cell(0, 6, 'Validity Period Distribution', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(1)

        short_90 = len([d for d in days if d <= 90])
        med_365 = len([d for d in days if 90 < d <= 365])
        long_730 = len([d for d in days if 365 < d <= 730])
        very_long = len([d for d in days if d > 730])

        buckets = [
            ('< 90 days', short_90, C['success']),
            ('90d - 1 year', med_365, C['primary']),
            ('1 - 2 years', long_730, C['warning']),
            ('> 2 years', very_long, C['danger']),
        ]
        max_b = max(b[1] for b in buckets) if buckets else 1
        for label, count, color in buckets:
            y = pdf.get_y()
            pdf.set_font(UCMReport.FONT, '', 8)
            pdf.set_text_color(*C['dark'])
            pdf.cell(28, 5, label)
            bw = pdf.h_bar(pdf.get_x(), y + 0.5, 100, count, max_b, color)
            pdf.set_x(pdf.get_x() + bw + 3)
            pdf.set_font(UCMReport.FONT, '', 7)
            pdf.set_text_color(*C['slate500'])
            pct = round(count / len(days) * 100) if days else 0
            pdf.cell(0, 5, '%d (%d%%)' % (count, pct), new_x='LMARGIN', new_y='NEXT')

        pdf.ln(2)
        if very_long > len(days) * 0.3:
            pdf.set_font(UCMReport.FONT, 'I', 7)
            pdf.set_text_color(*C['slate500'])
            pdf.multi_cell(0, 4, 'Note: >30% of certificates have lifetimes exceeding 2 years. Consider shorter validity periods for improved security.')
        elif short_90 > len(days) * 0.5:
            pdf.set_font(UCMReport.FONT, 'I', 7)
            pdf.set_text_color(*C['success'])
            pdf.multi_cell(0, 4, 'Good practice: Majority of certificates use short-lived validity (< 90 days).')

        pdf.ln(6)

    # -- 7. CA infrastructure ------------------------------------------

    @classmethod
    def _add_ca_section(cls, pdf, data):
        if pdf.get_y() > 220:
            pdf.add_page()
        pdf.section_title('7. CA Infrastructure', '%d Certificate Authorities' % data['total_cas'])

        y = pdf.get_y()
        cw = 60
        pdf.stat_card(10, y, cw, 22, data['total_cas'], 'Total CAs', C['primary'])
        pdf.stat_card(75, y, cw, 22, data['root_cas'], 'Root CAs', C['success'])
        pdf.stat_card(140, y, cw, 22, data['intermediate_cas'], 'Intermediate CAs', C['warning'])
        pdf.set_y(y + 28)

        cas = data.get('ca_list', [])
        if cas:
            widths = [60, 50, 30, 50]
            headers = ['CA Name', 'Key Algorithm', 'Type', 'Subject']
            pdf.table_header(widths, headers)
            for i, ca in enumerate(cas[:15]):
                name = (ca.descr or 'N/A')[:28]
                algo = (ca.key_type or 'N/A')[:22]
                ca_type = 'Root' if not ca.caref else 'Intermediate'
                subject = (ca.common_name or ca.subject or 'N/A')[:24]
                pdf.table_row(widths, [name, algo, ca_type, subject], i)

        pdf.ln(6)

    # -- 8. security & audit -------------------------------------------

    @classmethod
    def _add_audit_section(cls, pdf, data):
        if pdf.get_y() > 200:
            pdf.add_page()
        pdf.section_title('8. Security & Audit', 'Activity summary for the last 30 days')

        y = pdf.get_y()
        cw = 43
        gap = 5
        login_success = data['action_counts'].get('login_success', 0)
        pdf.stat_card(10, y, cw, 22, data['total_audit_events'], 'Total Events', C['primary'])
        pdf.stat_card(10 + cw + gap, y, cw, 22, login_success, 'Successful Logins', C['success'])
        pdf.stat_card(10 + 2 * (cw + gap), y, cw, 22, data['failed_logins'], 'Failed Logins',
                      C['danger'] if data['failed_logins'] > 10 else C['slate500'])
        pdf.stat_card(10 + 3 * (cw + gap), y, cw, 22, data['unique_users'], 'Active Users', C['accent_teal'])
        pdf.set_y(y + 28)

        pdf.set_font(UCMReport.FONT, 'B', 9)
        pdf.set_text_color(*C['dark'])
        pdf.cell(0, 6, 'Top Actions', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(1)

        top_actions = sorted(data['action_counts'].items(), key=lambda x: -x[1])[:10]
        max_a = top_actions[0][1] if top_actions else 1

        for action, count in top_actions:
            label = action.replace('_', ' ').title()
            y = pdf.get_y()
            pdf.set_font(UCMReport.FONT, '', 8)
            pdf.set_text_color(*C['dark'])
            pdf.cell(45, 5, label)
            bw = pdf.h_bar(pdf.get_x(), y + 0.5, 80, count, max_a, C['primary'])
            pdf.set_x(pdf.get_x() + bw + 3)
            pdf.set_font(UCMReport.FONT, '', 7)
            pdf.set_text_color(*C['slate500'])
            pdf.cell(0, 5, str(count), new_x='LMARGIN', new_y='NEXT')

        pdf.ln(6)

    # -- 9. recommendations --------------------------------------------

    @classmethod
    def _add_recommendations(cls, pdf, data):
        if pdf.get_y() > 200:
            pdf.add_page()
        pdf.section_title('9. Recommendations', 'Actionable improvements for your PKI posture')

        recs = []

        if data['expired_certs'] > 0:
            recs.append((
                'Remove Expired Certificates',
                '%d expired certificate(s) remain in inventory. '
                'Remove or renew them to reduce clutter and avoid accidental use.' % data['expired_certs'],
                'HIGH', C['danger']
            ))

        if len(data['expiring_30']) > 0:
            recs.append((
                'Renew Expiring Certificates',
                '%d certificate(s) expire within 30 days. '
                'Enable auto-renewal via ACME where possible to prevent outages.' % len(data['expiring_30']),
                'HIGH', C['warning']
            ))

        if data['avg_score'] < 70:
            recs.append((
                'Improve Compliance Score',
                'Current average score is %d/100. Review weak certificates '
                'for key strength, signature algorithms, and validity period issues.' % data['avg_score'],
                'HIGH', C['warning']
            ))

        manual_count = data['source_counts'].get('manual', 0)
        if manual_count > data['total_certs'] * 0.8 and data['total_certs'] > 5:
            recs.append((
                'Adopt Automated Certificate Management',
                '%d of %d certificates are manually managed. '
                'Consider ACME protocol integration for automated issuance and renewal.' % (manual_count, data['total_certs']),
                'MEDIUM', C['primary']
            ))

        long_lived = len([d for d in data['lifetime_days'] if d > 730])
        if long_lived > 0:
            recs.append((
                'Reduce Certificate Lifetimes',
                '%d certificate(s) have validity periods exceeding 2 years. '
                'Industry best practices recommend 90-day to 1-year maximum validity.' % long_lived,
                'MEDIUM', C['warning']
            ))

        weak_algos = sum(c for a, c in data['algo_counts'].items() if 'RSA 1024' in a.upper() or 'SHA1' in a.upper())
        if weak_algos > 0:
            recs.append((
                'Upgrade Weak Cryptography',
                '%d certificate(s) use weak algorithms. '
                'Migrate to RSA 2048+ or ECDSA P-256/P-384 with SHA-256+.' % weak_algos,
                'HIGH', C['danger']
            ))

        if data['failed_logins'] > 10:
            recs.append((
                'Review Failed Login Attempts',
                '%d failed login attempts in 30 days. '
                'Investigate potential brute-force attacks and consider stricter lockout policies.' % data['failed_logins'],
                'MEDIUM', C['warning']
            ))

        recs.append((
            'Regular Compliance Audits',
            'Schedule periodic compliance reviews to ensure all certificates meet '
            'organizational security policies and industry standards.',
            'LOW', C['primary']
        ))

        recs.append((
            'Enable Certificate Discovery',
            'Run network discovery scans regularly to detect unknown or shadow certificates '
            'across your infrastructure.',
            'LOW', C['accent_teal']
        ))

        for i, (title, desc, severity, color) in enumerate(recs):
            y = pdf.get_y()
            if y > 260:
                pdf.add_page()
                y = pdf.get_y()

            pdf.set_fill_color(*color)
            pdf.rect(10, y + 1, 18, 5, style='F')
            pdf.set_xy(10, y + 1)
            pdf.set_font(UCMReport.FONT, 'B', 6)
            pdf.set_text_color(*C['white'])
            pdf.cell(18, 5, severity, align='C')

            pdf.set_xy(32, y)
            pdf.set_font(UCMReport.FONT, 'B', 9)
            pdf.set_text_color(*C['dark'])
            pdf.cell(0, 7, title, new_x='LMARGIN', new_y='NEXT')

            pdf.set_x(32)
            pdf.set_font(UCMReport.FONT, '', 8)
            pdf.set_text_color(*C['slate600'])
            pdf.multi_cell(165, 4, desc)
            pdf.ln(3)

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _cert_status(cert, now):
        if cert.revoked:
            return 'revoked'
        if cert.valid_to:
            if cert.valid_to < now:
                return 'expired'
            if (cert.valid_to - now).days <= 30:
                return 'expiring'
        return 'valid'

    @staticmethod
    def _score_to_grade(score):
        if score >= 95:
            return 'A+'
        if score >= 85:
            return 'A'
        if score >= 70:
            return 'B'
        if score >= 55:
            return 'C'
        if score >= 40:
            return 'D'
        return 'F'
