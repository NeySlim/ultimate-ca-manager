"""Certificate-focused section builders: executive summary, risk, inventory, expiry, lifecycle."""
from .report_document import UCMReport
from .formatters import C
from utils.datetime_utils import utc_now


def _add_executive_summary(pdf, data):
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

    y = pdf.get_y()
    cw = 43
    gap = 5
    grade_color = C.get('grade_' + data['avg_grade'][0].lower(), C['slate500'])
    risk_color = (C['success'] if data['risk_level'] == 'LOW'
                  else C['warning'] if data['risk_level'] == 'MEDIUM' else C['danger'])
    pdf.stat_card(10, y, cw, 26, data['total_certs'], 'Total Certificates', C['primary'],
                  '%d active' % data['active_certs'])
    pdf.stat_card(10 + cw + gap, y, cw, 26, data['avg_grade'], 'Compliance Grade',
                  grade_color, '%d/100' % data['avg_score'])
    pdf.stat_card(10 + 2 * (cw + gap), y, cw, 26, data['total_cas'], 'CAs', C['primary'],
                  '%d root, %d intermediate' % (data['root_cas'], data['intermediate_cas']))
    pdf.stat_card(10 + 3 * (cw + gap), y, cw, 26, data['risk_level'], 'Risk Level', risk_color)
    pdf.set_y(y + 32)

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


def _add_risk_assessment(pdf, data):
    pdf.section_title('2. Risk Assessment', 'Identified risks and their severity levels')

    risk = data['risk_level']
    risk_color = C['success'] if risk == 'LOW' else C['warning'] if risk == 'MEDIUM' else C['danger']

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
            sc = (C['danger'] if severity == 'CRITICAL'
                  else C['warning'] if severity in ('HIGH', 'MEDIUM') else C['success'])
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


def _add_certificate_status(pdf, data):
    if pdf.get_y() > 200:
        pdf.add_page()
    pdf.section_title('3. Certificate Inventory', '%d certificates managed' % data['total_certs'])

    total = max(data['total_certs'], 1)

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

    pdf.set_font(UCMReport.FONT, '', 7)
    for label, count, color in statuses:
        pdf.set_fill_color(*color)
        pdf.rect(pdf.get_x(), pdf.get_y() + 1, 3, 3, style='F')
        pdf.set_x(pdf.get_x() + 5)
        pdf.set_text_color(*C['dark'])
        pct = round(count / total * 100) if total else 0
        pdf.cell(40, 5, '%s: %d (%d%%)' % (label, count, pct))
    pdf.ln(8)

    y_start = pdf.get_y()

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


def _add_expiry_section(pdf, data):
    if not data['expiring_30']:
        return
    if pdf.get_y() > 210:
        pdf.add_page()

    pdf.section_title('5. Expiring Certificates',
                      '%d certificate(s) expiring within 30 days' % len(data['expiring_30']))

    now = utc_now()
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


def _add_lifecycle_section(pdf, data):
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
