"""Cover page and table-of-contents section builders for UCM PDF reports."""
from .report_document import UCMReport, _cover_panel, _risk_gauge
from .formatters import C


def _add_cover_page(pdf, data):
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)

    pdf.set_fill_color(*C['dark'])
    pdf.rect(0, 0, 210, 297, style='F')

    pdf.set_fill_color(*C['primary'])
    pdf.rect(0, 0, 210, 5, style='F')

    pdf.set_xy(10, 14)
    pdf.set_font(UCMReport.FONT, 'B', 9)
    pdf.set_text_color(*C['primary'])
    pdf.cell(0, 6, 'ULTIMATE CA MANAGER')

    pdf.set_xy(160, 14)
    pdf.set_font(UCMReport.FONT, '', 8)
    pdf.set_text_color(*C['slate400'])
    pdf.cell(40, 6, 'v' + data['version'], align='R')

    pdf.set_xy(10, 38)
    pdf.set_font(UCMReport.FONT, 'B', 36)
    pdf.set_text_color(*C['white'])
    pdf.cell(0, 16, 'PKI Executive', new_x='LMARGIN', new_y='NEXT')
    pdf.set_x(10)
    pdf.cell(0, 16, 'Report', new_x='LMARGIN', new_y='NEXT')

    pdf.set_xy(10, 78)
    pdf.set_font(UCMReport.FONT, '', 11)
    pdf.set_text_color(*C['slate400'])
    pdf.cell(0, 7, data['generated_at'].strftime('%B %d, %Y'))

    pdf.set_draw_color(*C['primary'])
    pdf.set_line_width(0.6)
    pdf.line(10, 92, 200, 92)
    pdf.set_line_width(0.2)

    risk = data['risk_level']
    risk_color = C['success'] if risk == 'LOW' else C['warning'] if risk == 'MEDIUM' else C['danger']
    grade_color = C.get('grade_' + data['avg_grade'][0].lower(), C['slate500'])

    panel_w = 58
    panel_h = 46
    panel_gap = 8
    panel_y = 100

    _cover_panel(pdf, 10, panel_y, panel_w, panel_h,
                 'RISK ASSESSMENT', risk, risk_color,
                 'Score: %d / 100' % data['risk_score'])

    x2 = 10 + panel_w + panel_gap
    _cover_panel(pdf, x2, panel_y, panel_w, panel_h,
                 'COMPLIANCE GRADE',
                 '%s' % data['avg_grade'], grade_color,
                 '%d / 100 average' % data['avg_score'])

    x3 = x2 + panel_w + panel_gap
    _cover_panel(pdf, x3, panel_y, panel_w, panel_h,
                 'CERTIFICATES', str(data['total_certs']), C['primary'],
                 '%d active, %d expiring' % (data['active_certs'], len(data['expiring_30'])))

    gauge_y = panel_y + panel_h + 10
    _risk_gauge(pdf, 10, gauge_y, 190, data['risk_score'])

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

    pdf.set_draw_color(*C['slate700'])
    pdf.line(10, 275, 200, 275)
    pdf.set_xy(10, 276)
    pdf.set_font(UCMReport.FONT, 'I', 7)
    pdf.set_text_color(*C['slate500'])
    pdf.cell(95, 5, 'Confidential - Authorized personnel only')
    pdf.cell(95, 5, data['generated_at'].strftime('%B %d, %Y  %H:%M UTC'), align='R')

    pdf.set_auto_page_break(auto=True, margin=20)


def _add_toc(pdf, data):
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
