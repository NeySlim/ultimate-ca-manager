"""
Email Templates for UCM
Provides default and custom template rendering with variable substitution
"""

# UCM Logo as base64 PNG (80x80)
UCM_LOGO_B64 = "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"

DEFAULT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background-color:#f4f5f7;font-family:'Segoe UI',Roboto,Arial,sans-serif;-webkit-font-smoothing:antialiased;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f5f7;padding:32px 16px;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06);">

<!-- Header with logo -->
<tr>
<td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);padding:28px 32px;text-align:center;">
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;">
<tr>
<td style="vertical-align:middle;padding-right:14px;">
<img src="data:image/png;base64,{{logo}}" alt="UCM" width="44" height="44" style="display:block;border:0;border-radius:8px;" />
</td>
<td style="vertical-align:middle;">
<span style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:0.5px;">Ultimate CA Manager</span>
</td>
</tr>
</table>
</td>
</tr>

<!-- Title bar -->
<tr>
<td style="background-color:{{title_color}};padding:14px 32px;">
<span style="font-size:16px;font-weight:600;color:#ffffff;">{{title}}</span>
</td>
</tr>

<!-- Content -->
<tr>
<td style="padding:28px 32px;">
{{content}}
</td>
</tr>

<!-- Footer -->
<tr>
<td style="padding:20px 32px;border-top:1px solid #e5e7eb;background-color:#fafbfc;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr>
<td style="font-size:12px;color:#9ca3af;line-height:1.5;">
Sent at {{datetime}}<br>
<span style="color:#6b7280;">Ultimate CA Manager</span>
</td>
<td align="right" style="font-size:11px;color:#d1d5db;">
{{instance_url}}
</td>
</tr>
</table>
</td>
</tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def get_default_template():
    """Return the default email template HTML"""
    return DEFAULT_TEMPLATE


def render_template(template_html: str, title: str, title_color: str, content: str,
                    instance_url: str = '') -> str:
    """
    Render an email template with variable substitution.
    
    Variables:
    - {{logo}} - UCM logo as base64 PNG
    - {{title}} - Email title/subject  
    - {{title_color}} - Color for the title bar (hex)
    - {{content}} - Main HTML content
    - {{datetime}} - Current UTC datetime
    - {{instance_url}} - UCM instance URL
    """
    from datetime import datetime as dt
    
    html = template_html or DEFAULT_TEMPLATE
    
    html = html.replace('{{logo}}', UCM_LOGO_B64)
    html = html.replace('{{title}}', title)
    html = html.replace('{{title_color}}', title_color)
    html = html.replace('{{content}}', content)
    html = html.replace('{{datetime}}', dt.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'))
    html = html.replace('{{instance_url}}', instance_url)
    
    return html
