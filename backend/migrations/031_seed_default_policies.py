"""
Migration 031: Seed default certificate policies

Creates useful out-of-the-box policies that reflect real-world PKI best practices:
- Web TLS (BR-compliant 397-day max)
- Internal/Private PKI (2-year max, relaxed)
- Short-Lived Automation (90-day ACME-style)
- Code Signing (strong keys required)
- Wildcard Certificates (approval required)
"""
import json
from datetime import datetime


DEFAULT_POLICIES = [
    {
        'name': 'Web Server TLS (Public)',
        'description': 'CA/Browser Forum compliant policy for publicly-trusted TLS certificates. Enforces 397-day maximum validity and modern key types.',
        'policy_type': 'issuance',
        'priority': 10,
        'is_active': True,
        'notify_on_violation': True,
        'requires_approval': False,
        'min_approvers': 1,
        'rules': json.dumps({
            'max_validity_days': 397,
            'allowed_key_types': ['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384'],
            'required_extensions': ['keyUsage', 'extendedKeyUsage', 'subjectAltName'],
            'san_restrictions': {
                'max_dns_names': 100,
                'dns_pattern': '',
                'require_approval_for_external': False,
            },
        }),
    },
    {
        'name': 'Internal PKI (Private)',
        'description': 'Relaxed policy for internal services, development, and private infrastructure. Allows longer validity and all key types.',
        'policy_type': 'issuance',
        'priority': 20,
        'is_active': True,
        'notify_on_violation': True,
        'requires_approval': False,
        'min_approvers': 1,
        'rules': json.dumps({
            'max_validity_days': 730,
            'allowed_key_types': ['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521'],
            'required_extensions': ['keyUsage'],
            'san_restrictions': {
                'max_dns_names': 250,
                'dns_pattern': '',
                'require_approval_for_external': False,
            },
        }),
    },
    {
        'name': 'Short-Lived Automation',
        'description': 'Policy for ACME-issued and automated certificates. 90-day max validity encourages frequent rotation and reduces exposure from compromised keys.',
        'policy_type': 'issuance',
        'priority': 15,
        'is_active': True,
        'notify_on_violation': False,
        'requires_approval': False,
        'min_approvers': 1,
        'rules': json.dumps({
            'max_validity_days': 90,
            'allowed_key_types': ['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384'],
            'required_extensions': ['keyUsage', 'extendedKeyUsage'],
            'san_restrictions': {
                'max_dns_names': 50,
                'dns_pattern': '',
                'require_approval_for_external': False,
            },
        }),
    },
    {
        'name': 'Code Signing',
        'description': 'Strict policy for code signing certificates. Requires strong key types (RSA-4096 or ECDSA) and manager approval before issuance.',
        'policy_type': 'issuance',
        'priority': 5,
        'is_active': True,
        'notify_on_violation': True,
        'requires_approval': True,
        'min_approvers': 1,
        'rules': json.dumps({
            'max_validity_days': 365,
            'allowed_key_types': ['RSA-4096', 'EC-P256', 'EC-P384'],
            'required_extensions': ['keyUsage', 'extendedKeyUsage'],
            'san_restrictions': {
                'max_dns_names': 0,
                'dns_pattern': '',
                'require_approval_for_external': False,
            },
        }),
    },
    {
        'name': 'Wildcard Certificates',
        'description': 'Controls wildcard certificate issuance. Requires approval to prevent overly broad certificates that increase attack surface.',
        'policy_type': 'issuance',
        'priority': 8,
        'is_active': True,
        'notify_on_violation': True,
        'requires_approval': True,
        'min_approvers': 1,
        'rules': json.dumps({
            'max_validity_days': 397,
            'allowed_key_types': ['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384'],
            'required_extensions': ['keyUsage', 'extendedKeyUsage', 'subjectAltName'],
            'san_restrictions': {
                'max_dns_names': 10,
                'dns_pattern': '*.',
                'require_approval_for_external': True,
            },
        }),
    },
]


def upgrade(conn):
    cursor = conn.cursor()
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    for policy in DEFAULT_POLICIES:
        # Skip if already exists (idempotent)
        cursor.execute('SELECT id FROM certificate_policies WHERE name = ?', (policy['name'],))
        if cursor.fetchone():
            continue

        cursor.execute('''
            INSERT INTO certificate_policies
            (name, description, policy_type, priority, is_active, notify_on_violation,
             requires_approval, min_approvers, rules, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            policy['name'],
            policy['description'],
            policy['policy_type'],
            policy['priority'],
            1 if policy['is_active'] else 0,
            1 if policy['notify_on_violation'] else 0,
            1 if policy['requires_approval'] else 0,
            policy['min_approvers'],
            policy['rules'],
            now,
            'system',
        ))

    conn.commit()


def downgrade(conn):
    cursor = conn.cursor()
    for policy in DEFAULT_POLICIES:
        cursor.execute("DELETE FROM certificate_policies WHERE name = ? AND created_by = 'system'",
                       (policy['name'],))
    conn.commit()
