"""Report template and section definitions for UCM PDF reports."""

ALL_SECTIONS = [
    'executive_summary',
    'risk_assessment',
    'certificate_status',
    'compliance_overview',
    'expiry',
    'lifecycle',
    'ca_hierarchy',
    'audit',
    'recommendations',
]

TEMPLATES = {
    'executive': {
        'name': 'Executive Summary',
        'description': 'Complete overview with all sections',
        'sections': ['executive_summary', 'risk_assessment', 'certificate_status',
                     'compliance_overview', 'expiry', 'lifecycle', 'ca_hierarchy',
                     'audit', 'recommendations'],
    },
    'certificate_inventory': {
        'name': 'Certificate Inventory',
        'description': 'Certificate status, expiry timeline and lifecycle analysis',
        'sections': ['certificate_status', 'expiry', 'lifecycle'],
    },
    'compliance': {
        'name': 'Compliance Report',
        'description': 'Compliance scores, risk assessment and recommendations',
        'sections': ['compliance_overview', 'risk_assessment', 'recommendations'],
    },
    'ca_overview': {
        'name': 'CA Overview',
        'description': 'Certificate Authority hierarchy and trust chain details',
        'sections': ['ca_hierarchy', 'certificate_status'],
    },
    'security_audit': {
        'name': 'Security & Audit',
        'description': 'Audit log summary, risk assessment and security posture',
        'sections': ['audit', 'risk_assessment', 'recommendations'],
    },
}
