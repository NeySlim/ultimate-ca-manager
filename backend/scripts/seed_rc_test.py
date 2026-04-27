#!/usr/bin/env python3
"""
Seed UCM database with a known-state mock dataset for Release Candidate testing.

USAGE:
    sudo systemctl stop ucm
    sudo python3 /opt/ucm/backend/scripts/seed_rc_test.py
    sudo systemctl start ucm

WHAT IT SEEDS:
    Users:
        admin    / changeme123  (admin role)
        operator / changeme123  (operator role)
        viewer   / changeme123  (viewer role)
    CAs:
        Test Root CA           (RSA-4096, 10y)
        Test Intermediate CA   (ECDSA-P256, 5y, signed by root, CDP enabled)
    Certificates:
        valid-1y.example.test   (valid, 1y remaining)
        expiring-soon.example.test (expires in 7 days)
        expired.example.test    (expired 30 days ago)
        wildcard.example.test   (*.example.test, 6m remaining)
        client-auth.example.test (TLS client cert)

DESTRUCTIVE: drops all tables and recreates them. Backup first if needed.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timedelta, timezone

from app import create_app
from models import db, User, CA, Certificate
from services.ca_service import CAService
from services.cert_service import CertificateService
from werkzeug.security import generate_password_hash


def seed():
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("UCM RC Test Seed")
        print("=" * 60)

        print("\n[1/4] Dropping and recreating all tables...")
        db.drop_all()
        db.create_all()

        print("\n[2/4] Creating users...")
        users = [
            User(
                username='admin',
                password_hash=generate_password_hash('changeme123'),
                email='admin@example.test',
                role='admin',
            ),
            User(
                username='operator',
                password_hash=generate_password_hash('changeme123'),
                email='operator@example.test',
                role='operator',
            ),
            User(
                username='viewer',
                password_hash=generate_password_hash('changeme123'),
                email='viewer@example.test',
                role='viewer',
            ),
        ]
        db.session.add_all(users)
        db.session.commit()
        for u in users:
            print(f"  - {u.username} ({u.role})")

        print("\n[3/4] Creating CAs...")
        base_dn = {
            'O': 'UCM RC Test',
            'OU': 'Testing',
            'C': 'US',
            'ST': 'Test',
            'L': 'Test',
        }
        root_ca = CAService.create_internal_ca(
            descr='Test Root CA',
            dn={**base_dn, 'CN': 'Test Root CA'},
            key_type='4096',
            validity_days=3650,
            digest='sha256',
        )
        print(f"  - {root_ca.descr} (root, RSA-4096, refid={root_ca.refid})")

        intermediate_ca = CAService.create_internal_ca(
            descr='Test Intermediate CA',
            dn={**base_dn, 'CN': 'Test Intermediate CA'},
            key_type='prime256v1',
            validity_days=1825,
            digest='sha256',
            caref=root_ca.refid,
        )
        intermediate_ca.cdp_enabled = True
        intermediate_ca.cdp_url = 'https://localhost/cdp/{ca_refid}.crl'
        db.session.commit()
        print(f"  - {intermediate_ca.descr} (intermediate, ECDSA-P256, CDP enabled, refid={intermediate_ca.refid})")

        print("\n[4/4] Creating leaf certificates...")
        leaf_specs = [
            # (CN, validity_days, label, sans)
            ('valid-1y.example.test', 365, 'valid (1y)', ['valid-1y.example.test']),
            ('expiring-soon.example.test', 7, 'expiring (7d)', ['expiring-soon.example.test']),
            ('wildcard.example.test', 180, 'wildcard (6m)', ['*.example.test', 'example.test']),
            ('client-auth.example.test', 365, 'client auth', ['client-auth.example.test']),
        ]
        for cn, days, label, sans in leaf_specs:
            try:
                cert = CertificateService.create_certificate(
                    descr=cn,
                    caref=intermediate_ca.refid,
                    dn={'CN': cn, 'O': 'UCM RC Test', 'C': 'US'},
                    cert_type='server_cert',
                    key_type='2048',
                    validity_days=days,
                    digest='sha256',
                    san_dns=sans,
                )
                print(f"  - {cn} [{label}]")
            except Exception as e:
                print(f"  ! Failed to issue {cn}: {e}")

        # Issue an expired cert by issuing with 1 day then back-dating
        try:
            expired = CertificateService.create_certificate(
                descr='expired.example.test',
                caref=intermediate_ca.refid,
                dn={'CN': 'expired.example.test', 'O': 'UCM RC Test', 'C': 'US'},
                cert_type='server_cert',
                key_type='2048',
                validity_days=1,
                digest='sha256',
                san_dns=['expired.example.test'],
            )
            # Force expired: set expires_at in past
            expired_at = datetime.now(timezone.utc) - timedelta(days=30)
            expired.expires_at = expired_at
            db.session.commit()
            print(f"  - expired.example.test [expired 30d ago, forced]")
        except Exception as e:
            print(f"  ! Failed to issue expired cert: {e}")

        print("\n" + "=" * 60)
        print("Seed complete.")
        print("=" * 60)
        print(f"Users:        {User.query.count()}")
        print(f"CAs:          {CA.query.count()}")
        print(f"Certificates: {Certificate.query.filter(Certificate.crt.isnot(None)).count()}")
        print()
        print("Login: admin / changeme123")
        print()
        print("Next: restart the service and run through the RC smoke-test checklist.")


if __name__ == '__main__':
    seed()
