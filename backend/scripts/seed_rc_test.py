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

        ca_service = CAService()
        cert_service = CertificateService()

        print("\n[3/4] Creating CAs...")
        root_ca = ca_service.create_internal_ca(
            common_name='Test Root CA',
            organization='UCM RC Test',
            organizational_unit='Testing',
            country='US',
            state='Test',
            locality='Test',
            validity_days=3650,
            key_type='RSA_4096',
            hash_algorithm='SHA256',
        )
        print(f"  - {root_ca.common_name} (root, RSA-4096)")

        intermediate_ca = ca_service.create_internal_ca(
            common_name='Test Intermediate CA',
            organization='UCM RC Test',
            organizational_unit='Testing',
            country='US',
            state='Test',
            locality='Test',
            validity_days=1825,
            key_type='ECDSA_P256',
            hash_algorithm='SHA256',
            parent_ca_id=root_ca.id,
        )
        intermediate_ca.cdp_enabled = True
        intermediate_ca.cdp_url = 'https://localhost/cdp/{ca_refid}.crl'
        db.session.commit()
        print(f"  - {intermediate_ca.common_name} (intermediate, ECDSA-P256, CDP enabled)")

        print("\n[4/4] Creating leaf certificates...")
        leaf_specs = [
            # (CN, validity_days, label)
            ('valid-1y.example.test', 365, 'valid (1y)'),
            ('expiring-soon.example.test', 7, 'expiring (7d)'),
            ('wildcard.example.test', 180, 'wildcard (6m)'),
            ('client-auth.example.test', 365, 'client auth'),
        ]
        for cn, days, label in leaf_specs:
            try:
                cert = cert_service.issue_certificate(
                    ca_id=intermediate_ca.id,
                    common_name=cn,
                    organization='UCM RC Test',
                    country='US',
                    validity_days=days,
                    key_type='RSA_2048',
                    hash_algorithm='SHA256',
                    san_dns=[cn] if not cn.startswith('wildcard') else ['*.example.test'],
                )
                print(f"  - {cn} [{label}]")
            except Exception as e:
                print(f"  ! Failed to issue {cn}: {e}")

        # Issue an expired cert by issuing with 1 day then back-dating
        try:
            expired = cert_service.issue_certificate(
                ca_id=intermediate_ca.id,
                common_name='expired.example.test',
                organization='UCM RC Test',
                country='US',
                validity_days=1,
                key_type='RSA_2048',
                hash_algorithm='SHA256',
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
        print("Next: restart the service and run through RELEASE_TESTING.md checklist.")


if __name__ == '__main__':
    seed()
