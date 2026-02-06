#!/usr/bin/env python3
"""
Add diverse certificates to demo database
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from models import db, CA, Certificate
from services.cert_service import CertificateService
import random

app = create_app()

with app.app_context():
    # Get CAs
    root_ca = CA.query.filter(CA.descr.like('%Root CA%')).first()
    web_ca = CA.query.filter(CA.descr.like('%Web Services%')).first()
    vpn_ca = CA.query.filter(CA.descr.like('%VPN Services%')).first()
    code_ca = CA.query.filter(CA.descr.like('%Code Signing%')).first()
    
    if not all([root_ca, web_ca, vpn_ca, code_ca]):
        print("❌ CAs not found! Run create_demo_cas.py first")
        sys.exit(1)
    
    print(f"✅ Found 4 CAs")
    print(f"   Root CA: {root_ca.refid}")
    print(f"   Web CA: {web_ca.refid}")
    print(f"   VPN CA: {vpn_ca.refid}")
    print(f"   Code CA: {code_ca.refid}")
    
    cert_service = CertificateService()
    
    print("\n📜 Creating Web Server Certificates...")
    
    # Wildcard certificate
    print("  🌐 Creating wildcard certificate...")
    wildcard = cert_service.create_certificate(
        descr='Wildcard *.certific.ate',
        caref=web_ca.refid,
        dn={
            'CN': '*.certific.ate',
            'O': 'Certific.ate Security',
            'OU': 'Web Services',
            'C': 'US'
        },
        cert_type='server_cert',
        key_type='prime256v1',
        validity_days=365,
        digest='sha256',
        san_dns=['*.certific.ate', 'certific.ate'],
        username='admin'
    )
    print(f"    ✅ {wildcard.descr}")
    
    # Individual web servers
    web_servers = [
        ('www.certific.ate', ['www.certific.ate', 'certific.ate']),
        ('api.certific.ate', ['api.certific.ate']),
        ('dashboard.certific.ate', ['dashboard.certific.ate']),
        ('mail.certific.ate', ['mail.certific.ate', 'smtp.certific.ate', 'imap.certific.ate']),
        ('shop.certific.ate', ['shop.certific.ate', 'store.certific.ate']),
        ('blog.certific.ate', ['blog.certific.ate']),
    ]
    
    for cn, sans in web_servers:
        cert = cert_service.create_certificate(
            descr=f'Web Server - {cn}',
            caref=web_ca.refid,
            dn={
                'CN': cn,
                'O': 'Certific.ate Security',
                'OU': 'Web Services',
                'C': 'US'
            },
            cert_type='server_cert',
            key_type='prime256v1',
            validity_days=730,
            digest='sha256',
            san_dns=sans,
            username='admin'
        )
        print(f"    ✅ {cn}")
    
    print("\n📜 Creating VPN Certificates...")
    
    # VPN Server
    vpn_server = cert_service.create_certificate(
        descr='VPN Server - vpn.certific.ate',
        caref=vpn_ca.refid,
        dn={
            'CN': 'vpn.certific.ate',
            'O': 'Certific.ate Security',
            'OU': 'Network Security',
            'C': 'US'
        },
        cert_type='server_cert',
        key_type='2048',
        validity_days=1095,
        digest='sha256',
        san_dns=['vpn.certific.ate'],
        san_ip=['10.0.0.1', '192.168.1.1'],
        username='admin'
    )
    print(f"    ✅ VPN Server: {vpn_server.descr}")
    
    # VPN Clients
    vpn_users = ['alice', 'bob', 'charlie', 'diana', 'eve']
    for user in vpn_users:
        cert = cert_service.create_certificate(
            descr=f'VPN Client - {user}@certific.ate',
            caref=vpn_ca.refid,
            dn={
                'CN': f'{user}@certific.ate',
                'O': 'Certific.ate Security',
                'OU': 'VPN Users',
                'C': 'US'
            },
            cert_type='usr_cert',
            key_type='2048',
            validity_days=365,
            digest='sha256',
            san_email=[f'{user}@certific.ate'],
            username='admin'
        )
        print(f"    ✅ VPN Client: {user}@certific.ate")
    
    print("\n📜 Creating Code Signing Certificates...")
    
    code_signers = [
        'Certific.ate Developers',
        'Certific.ate Release Team',
        'Alice Developer',
        'Bob DevOps',
    ]
    
    for signer in code_signers:
        cert = cert_service.create_certificate(
            descr=f'Code Signing - {signer}',
            caref=code_ca.refid,
            dn={
                'CN': signer,
                'O': 'Certific.ate Security',
                'OU': 'Engineering',
                'C': 'US'
            },
            cert_type='usr_cert',
            key_type='4096',
            validity_days=1095,
            digest='sha512',
            username='admin'
        )
        print(f"    ✅ Code Signing: {signer}")
    
    print("\n📜 Creating Email (S/MIME) Certificates...")
    
    emails = [
        'admin@certific.ate',
        'alice@certific.ate',
        'bob@certific.ate',
        'security@certific.ate',
        'support@certific.ate',
    ]
    
    for email in emails:
        cert = cert_service.create_certificate(
            descr=f'Email - {email}',
            caref=web_ca.refid,
            dn={
                'CN': email,
                'O': 'Certific.ate Security',
                'OU': 'Email Security',
                'C': 'US'
            },
            cert_type='usr_cert',
            key_type='2048',
            validity_days=730,
            digest='sha256',
            san_email=[email],
            username='admin'
        )
        print(f"    ✅ Email: {email}")
    
    print("\n🗑️  Revoking some certificates for CRL demo...")
    
    # Get all certificates
    all_certs = Certificate.query.all()
    
    # Revoke 3-4 random certificates
    to_revoke = random.sample(all_certs, min(4, len(all_certs)))
    
    for cert in to_revoke:
        # Use cert_service revoke if available, otherwise direct update
        cert.revoked = True
        cert.revoked_at = db.func.now()
        print(f"    ✅ Revoked: {cert.descr}")
    
    db.session.commit()
    
    # Generate CRLs for CAs with CDP
    print("\n🔄 Generating CRLs...")
    from services.crl_service import CRLService
    crl_service = CRLService()
    
    try:
        crl_service.generate_crl(web_ca.id)
        print(f"    ✅ CRL generated for Web Services CA")
    except Exception as e:
        print(f"    ⚠️  CRL generation skipped for Web CA: {e}")
    
    try:
        crl_service.generate_crl(vpn_ca.id)
        print(f"    ✅ CRL generated for VPN Services CA")
    except Exception as e:
        print(f"    ⚠️  CRL generation skipped for VPN CA: {e}")
    
    print("\n" + "="*70)
    print("✅ CERTIFICATES ADDED!")
    print("="*70)
    print(f"📊 Final Statistics:")
    print(f"   CAs: {CA.query.count()}")
    print(f"   Total Certificates: {Certificate.query.count()}")
    print(f"   Active: {Certificate.query.filter_by(revoked=False).count()}")
    print(f"   Revoked: {Certificate.query.filter_by(revoked=True).count()}")
    print(f"\nBreakdown:")
    print(f"   Web Servers: 7 (wildcard + 6 servers)")
    print(f"   VPN: 6 (1 server + 5 clients)")
    print(f"   Code Signing: 4")
    print(f"   Email (S/MIME): 5")
    print(f"   Total: {7+6+4+5} certificates")
    print("="*70)
