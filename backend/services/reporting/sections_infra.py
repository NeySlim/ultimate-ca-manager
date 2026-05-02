"""Infrastructure section builders: compliance overview, CA hierarchy, audit, recommendations."""
from .report_document import UCMReport
from .formatters import C


def _add_compliance_overview(pdf, data):
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


def _add_ca_section(pdf, data):
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


def _add_audit_section(pdf, data):
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


def _add_recommendations(pdf, data):
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
