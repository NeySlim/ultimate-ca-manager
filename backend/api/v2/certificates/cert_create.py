"""Certificate create route"""
import re
import logging
import base64
import uuid
import json
from datetime import timedelta
from ipaddress import ip_address
from flask import request, g
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response
from utils.dn_validation import validate_dn_field
from utils.eku_validation import normalize_extra_ekus, to_object_identifiers, merge_eku_lists
from models import Certificate, CA, db
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID, ExtensionOID
from services.audit_service import AuditService
from services.notification_service import NotificationService
from security.encryption import decrypt_private_key
from websocket.emitters import on_certificate_issued
from utils.datetime_utils import utc_now, utc_isoformat
from utils.db_transaction import safe_commit
from . import bp

logger = logging.getLogger(__name__)


@bp.route('/api/v2/certificates', methods=['POST'])
@require_auth(['write:certificates'])
def create_certificate():
    """Create certificate - Real implementation"""

    data = request.json

    if not data or not data.get('cn'):
        return error_response('Common Name (cn) is required', 400)

    if not data.get('ca_id'):
        return error_response('CA ID is required', 400)

    # SECURITY: Validate DN fields
    dn_validations = [
        ('CN', data.get('cn')),
        ('O', data.get('organization')),
        ('OU', data.get('organizational_unit')),
        ('C', (data.get('country') or '').upper() or None),
        ('ST', data.get('state')),
        ('L', data.get('locality')),
    ]
    for field_name, value in dn_validations:
        is_valid, error = validate_dn_field(field_name, value)
        if not is_valid:
            return error_response(error, 400)

    # Parse SAN string into typed arrays if not already provided
    if data.get('san') and not data.get('san_dns'):
        san_dns = []
        san_ip = []
        san_email = []
        san_uri = []
        san_raw = data['san']
        # Accept both string and array
        if isinstance(san_raw, list):
            san_raw = ','.join(str(s) for s in san_raw)
        raw_sans = [s.strip() for s in re.split(r'[,\n;]+', san_raw) if s.strip()]
        for entry in raw_sans:
            entry_lower = entry.lower()
            # Check explicit type prefixes
            if entry_lower.startswith('uri:'):
                san_uri.append(re.sub(r'^URI:\s*', '', entry, flags=re.IGNORECASE))
                continue
            if entry_lower.startswith('email:'):
                san_email.append(re.sub(r'^EMAIL:\s*', '', entry, flags=re.IGNORECASE))
                continue
            # Remove type prefixes if present (e.g. "DNS:example.com", "IP:1.2.3.4")
            entry_clean = re.sub(r'^(DNS|IP):\s*', '', entry, flags=re.IGNORECASE)
            if not entry_clean:
                continue
            try:
                ip_address(entry_clean)
                san_ip.append(entry_clean)
            except ValueError:
                if '@' in entry_clean:
                    san_email.append(entry_clean)
                elif entry_clean.startswith('http://') or entry_clean.startswith('https://'):
                    san_uri.append(entry_clean)
                else:
                    san_dns.append(entry_clean)
        if san_dns:
            data['san_dns'] = san_dns
        if san_ip:
            data['san_ip'] = san_ip
        if san_email:
            data['san_email'] = san_email
        if san_uri:
            data['san_uri'] = san_uri

    # Get the CA
    ca = CA.query.get(data['ca_id'])
    if not ca:
        return error_response('CA not found', 404)

    if not ca.prv:
        return error_response('CA private key not available', 400)

    # Policy evaluation — check if approval is required (admins bypass)
    try:
        user_role = getattr(g.current_user, 'role', None) if hasattr(g, 'current_user') else None
        if user_role != 'admin':
            from services.policy_service import PolicyEvaluationService
            san_list = data.get('san', [])
            if isinstance(san_list, str):
                san_list = [s.strip() for s in san_list.split(',') if s.strip()]
            policy = PolicyEvaluationService.check_approval_required(
                ca_id=ca.id,
                template_id=data.get('template_id'),
                cn=data.get('cn'),
                san_list=san_list
            )
            if policy:
                user_id = g.current_user.id if hasattr(g, 'current_user') else None
                if not user_id:
                    return error_response('Authentication required for approval workflow', 401)
                approval = PolicyEvaluationService.create_approval_request(
                    policy=policy,
                    request_data=data,
                    requester_id=user_id,
                    comment=data.get('approval_comment')
                )
                return success_response(
                    data={
                        'approval_required': True,
                        'approval_id': approval.id,
                        'policy_name': policy.name,
                        'status': 'pending_approval',
                        'message': f'Certificate request requires approval per policy "{policy.name}"'
                    },
                    message='Certificate request submitted for approval'
                )
    except Exception as e:
        logger.warning(f"Policy evaluation failed (non-blocking): {e}")

    try:
        # Load CA certificate and key
        ca_cert_pem = base64.b64decode(ca.crt)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
        ca_key_pem = base64.b64decode(decrypt_private_key(ca.prv))
        ca_key = serialization.load_pem_private_key(ca_key_pem, password=None, backend=default_backend())

        # Generate key pair
        key_type = data.get('key_type', 'RSA')
        key_size = data.get('key_size', '2048')

        # Validate RSA key size
        if key_type.upper() not in ('EC', 'ECDSA'):
            if int(key_size) < 2048:
                return error_response('RSA key size must be at least 2048 bits', 400)

        if key_type.upper() in ('EC', 'ECDSA'):
            # Map key_size to curve name if needed
            curve_map = {
                '256': 'secp256r1', 'prime256v1': 'secp256r1', 'secp256r1': 'secp256r1',
                '384': 'secp384r1', 'secp384r1': 'secp384r1',
                '521': 'secp521r1', 'secp521r1': 'secp521r1',
            }
            curve_name = curve_map.get(str(key_size), data.get('curve', 'secp256r1'))
            curves = {
                'secp256r1': ec.SECP256R1(),
                'secp384r1': ec.SECP384R1(),
                'secp521r1': ec.SECP521R1(),
            }
            curve = curves.get(curve_name, ec.SECP256R1())
            new_key = ec.generate_private_key(curve, default_backend())
        else:
            new_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=int(key_size),
                backend=default_backend()
            )

        # Build subject
        subject_attrs = [x509.NameAttribute(NameOID.COMMON_NAME, data['cn'])]
        if data.get('organization'):
            subject_attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, data['organization']))
        if data.get('organizational_unit'):
            subject_attrs.append(x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, data['organizational_unit']))
        if data.get('country'):
            subject_attrs.append(x509.NameAttribute(NameOID.COUNTRY_NAME, data['country'].upper()))
        if data.get('state'):
            subject_attrs.append(x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, data['state']))
        if data.get('locality'):
            subject_attrs.append(x509.NameAttribute(NameOID.LOCALITY_NAME, data['locality']))
        if data.get('email'):
            subject_attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, data['email']))

        subject = x509.Name(subject_attrs)

        # Validity
        validity_days = data.get('validity_days', 365)
        now = utc_now()
        not_before = now
        not_after = now + timedelta(days=validity_days)

        # Build certificate
        builder = x509.CertificateBuilder()
        builder = builder.subject_name(subject)
        builder = builder.issuer_name(ca_cert.subject)
        builder = builder.public_key(new_key.public_key())
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.not_valid_before(not_before)
        builder = builder.not_valid_after(not_after)

        # Basic Constraints (not a CA)
        builder = builder.add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True
        )

        # Key Usage & Extended Key Usage based on cert_type
        cert_type = data.get('cert_type', 'server')

        # Define profiles for each certificate type
        cert_profiles = {
            'server': {
                'ku': dict(digital_signature=True, key_encipherment=True, content_commitment=False,
                           data_encipherment=False, key_agreement=False, key_cert_sign=False,
                           crl_sign=False, encipher_only=False, decipher_only=False),
                'eku': [ExtendedKeyUsageOID.SERVER_AUTH],
            },
            'client': {
                'ku': dict(digital_signature=True, key_encipherment=False, content_commitment=False,
                           data_encipherment=False, key_agreement=False, key_cert_sign=False,
                           crl_sign=False, encipher_only=False, decipher_only=False),
                'eku': [ExtendedKeyUsageOID.CLIENT_AUTH],
            },
            'combined': {
                'ku': dict(digital_signature=True, key_encipherment=True, content_commitment=False,
                           data_encipherment=False, key_agreement=False, key_cert_sign=False,
                           crl_sign=False, encipher_only=False, decipher_only=False),
                'eku': [ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH],
            },
            'code_signing': {
                'ku': dict(digital_signature=True, key_encipherment=False, content_commitment=False,
                           data_encipherment=False, key_agreement=False, key_cert_sign=False,
                           crl_sign=False, encipher_only=False, decipher_only=False),
                'eku': [ExtendedKeyUsageOID.CODE_SIGNING],
            },
            'email': {
                'ku': dict(digital_signature=True, key_encipherment=True, content_commitment=True,
                           data_encipherment=False, key_agreement=False, key_cert_sign=False,
                           crl_sign=False, encipher_only=False, decipher_only=False),
                'eku': [ExtendedKeyUsageOID.EMAIL_PROTECTION],
            },
        }

        profile = cert_profiles.get(cert_type, cert_profiles['server'])
        builder = builder.add_extension(x509.KeyUsage(**profile['ku']), critical=True)

        # Custom Extended Key Usage OIDs (RFC 5280 §4.2.1.12)
        extra_ekus_input = data.get('extra_ekus')
        extra_oid_strs, extra_err = normalize_extra_ekus(extra_ekus_input)
        if extra_err:
            return error_response(f'Invalid extra_ekus: {extra_err}', 400)
        eku_oids = merge_eku_lists(profile['eku'], to_object_identifiers(extra_oid_strs))
        builder = builder.add_extension(x509.ExtendedKeyUsage(eku_oids), critical=False)

        # Subject Alternative Names
        san_list = []
        if data.get('san_dns'):
            for dns in data['san_dns']:
                san_list.append(x509.DNSName(dns))
        if data.get('san_ip'):
            for ip in data['san_ip']:
                san_list.append(x509.IPAddress(ip_address(ip)))
        if data.get('san_email'):
            for email in data['san_email']:
                san_list.append(x509.RFC822Name(email))
        if data.get('san_uri'):
            for uri in data['san_uri']:
                san_list.append(x509.UniformResourceIdentifier(uri))

        # Auto-add CN as SAN based on cert type
        cn = data['cn']
        cn_looks_like_hostname = '.' in cn or cn.startswith('*')
        cn_looks_like_email = '@' in cn and '.' in cn.split('@')[-1]

        # Server/combined: CN → DNS SAN
        if cert_type in ['server', 'combined'] and cn_looks_like_hostname and cn not in (data.get('san_dns') or []):
            san_list.insert(0, x509.DNSName(cn))

        # Email/combined: CN → Email SAN (if CN is an email address)
        if cert_type in ['email', 'combined'] and cn_looks_like_email and cn not in (data.get('san_email') or []):
            san_list.insert(0, x509.RFC822Name(cn))

        # Email/combined: Subject email → Email SAN
        subject_email = data.get('email', '')
        if cert_type in ['email', 'combined'] and subject_email and '@' in subject_email:
            if subject_email != cn and subject_email not in (data.get('san_email') or []):
                existing_emails = [str(s.value) for s in san_list if isinstance(s, x509.RFC822Name)]
                if subject_email not in existing_emails:
                    san_list.append(x509.RFC822Name(subject_email))

        # Derive final SAN lists from san_list so auto-added entries are
        # reflected in the DB columns, not just the X.509 extension.
        final_san_dns = [s.value for s in san_list if isinstance(s, x509.DNSName)]
        final_san_ip = [str(s.value) for s in san_list if isinstance(s, x509.IPAddress)]
        final_san_email = [s.value for s in san_list if isinstance(s, x509.RFC822Name)]
        final_san_uri = [s.value for s in san_list if isinstance(s, x509.UniformResourceIdentifier)]

        if san_list:
            builder = builder.add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False
            )

        # Subject Key Identifier
        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(new_key.public_key()),
            critical=False
        )

        # Authority Key Identifier
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False
        )

        # CRL Distribution Points — embed CA's CDP URLs if enabled
        if ca.cdp_enabled:
            cdp_urls = [url.replace('{ca_refid}', ca.refid) for url in ca.get_cdp_urls()]
            if cdp_urls:
                dist_points = [
                    x509.DistributionPoint(
                        full_name=[x509.UniformResourceIdentifier(url)],
                        relative_name=None,
                        reasons=None,
                        crl_issuer=None
                    )
                    for url in cdp_urls
                ]
                builder = builder.add_extension(
                    x509.CRLDistributionPoints(dist_points),
                    critical=False
                )

        # Authority Information Access — embed OCSP/AIA URLs if enabled
        aia_descriptions = []
        if ca.ocsp_enabled:
            for uri in ca.get_ocsp_urls():
                aia_descriptions.append(
                    x509.AccessDescription(
                        x509.oid.AuthorityInformationAccessOID.OCSP,
                        x509.UniformResourceIdentifier(uri)
                    )
                )
        if ca.aia_ca_issuers_enabled:
            for url in ca.get_aia_urls():
                aia_descriptions.append(
                    x509.AccessDescription(
                        x509.oid.AuthorityInformationAccessOID.CA_ISSUERS,
                        x509.UniformResourceIdentifier(url.replace('{ca_refid}', ca.refid))
                    )
                )
        if aia_descriptions:
            builder = builder.add_extension(
                x509.AuthorityInformationAccess(aia_descriptions),
                critical=False
            )

        # Certificate Policies / CPS
        if ca.cps_enabled and ca.cps_uri:
            policy_oid = x509.ObjectIdentifier(ca.cps_oid or '2.5.29.32.0')
            builder = builder.add_extension(
                x509.CertificatePolicies([
                    x509.PolicyInformation(
                        policy_identifier=policy_oid,
                        policy_qualifiers=[ca.cps_uri]
                    )
                ]),
                critical=False
            )

        # OCSP Must-Staple / TLS Feature (RFC 6066)
        if data.get('ocsp_must_staple'):
            builder = builder.add_extension(
                x509.TLSFeature([x509.TLSFeatureType.status_request]),
                critical=False,
            )

        # Sign certificate
        new_cert = builder.sign(ca_key, hashes.SHA256(), default_backend())

        # Serialize
        cert_pem = new_cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
        key_pem = new_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        # Save to database
        # Extract SKI/AKI from issued cert
        cert_ski = None
        cert_aki = None
        try:
            ext = new_cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
            cert_ski = ext.value.key_identifier.hex(':').upper()
        except Exception:
            pass
        try:
            ext = new_cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
            if ext.value.key_identifier:
                cert_aki = ext.value.key_identifier.hex(':').upper()
        except Exception:
            pass

        db_cert = Certificate(
            refid=str(uuid.uuid4())[:8],
            descr=data.get('description', data['cn']),
            caref=ca.refid,
            crt=base64.b64encode(cert_pem.encode()).decode(),
            prv=base64.b64encode(key_pem.encode()).decode(),
            cert_type=cert_type,
            subject=new_cert.subject.rfc4514_string(),
            issuer=new_cert.issuer.rfc4514_string(),
            serial_number=format(new_cert.serial_number, 'x'),
            aki=cert_aki,
            ski=cert_ski,
            valid_from=not_before,
            valid_to=not_after,
            san_dns=json.dumps(final_san_dns),
            san_ip=json.dumps(final_san_ip),
            san_email=json.dumps(final_san_email),
            san_uri=json.dumps(final_san_uri),
            ocsp_must_staple=bool(data.get('ocsp_must_staple')),
            created_by=g.current_user.username if hasattr(g, 'current_user') else None
        )

        db.session.add(db_cert)
        ok, err = safe_commit(logger, "Failed to create certificate")
        if not ok:
            return err

        # Audit log
        try:
            AuditService.log_action(
                action='certificate_created',
                resource_type='certificate',
                resource_id=str(db_cert.id),
                resource_name=data['cn'],
                details=f"CA: {ca.id}, CN: {data['cn']}",
                user_id=g.current_user.id if hasattr(g, 'current_user') else None
            )
        except Exception:
            pass

        # Send notification
        try:
            username = g.current_user.username if hasattr(g, 'current_user') else 'system'
            NotificationService.on_certificate_issued(db_cert, username)
        except Exception:
            pass  # Non-blocking

        # WebSocket event
        try:
            on_certificate_issued(
                cert_id=db_cert.id,
                cn=data['cn'],
                ca_id=ca.id,
                issuer=ca.name,
                valid_to=utc_isoformat(not_after)
            )
        except Exception:
            pass  # Non-blocking

        return created_response(
            data=db_cert.to_dict(),
            message='Certificate created successfully'
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create certificate: {e}")
        return error_response('Failed to create certificate', 500)
