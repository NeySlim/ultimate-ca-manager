"""Certificate create route"""
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
from models import Certificate, CertificateTemplate, CA, db
from services.trust_store.constants import HASH_ALGORITHMS
from services.trust_store.constraints_mixin import validate_name_constraints
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID, ExtensionOID
from services.audit_service import AuditService
from services.notification_service import NotificationService
from websocket.emitters import on_certificate_issued
from utils.datetime_utils import utc_now, utc_isoformat, cert_not_before
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

    from utils.san_parse import parse_cert_san_payload

    san_buckets, san_err = parse_cert_san_payload(data)
    if san_err:
        return error_response(san_err, 400)
    for key, values in san_buckets.items():
        if values:
            data[key] = values

    # Get the CA
    ca = db.session.get(CA, data['ca_id'])
    if not ca:
        return error_response('CA not found', 404)

    # Resolve template: its digest is honored at signing and the link is
    # persisted on the issued row (usage counting, "template used" display)
    template = None
    if data.get('template_id'):
        template = db.session.get(CertificateTemplate, data['template_id'])
        if not template:
            return error_response('Template not found', 404)

    if not ca.has_private_key:
        return error_response('CA private key not available', 400)

    if ca.offline:
        return error_response('CA is offline; restore it before issuing', 400)

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
        from services.hsm.ca_key_loader import get_ca_signing_key
        ca_key = get_ca_signing_key(ca)

        from utils.key_type import parse_issue_key_type

        key_type_in = data.get('key_type') or data.get('keyType', 'rsa')
        key_size_in = data.get('key_size') or data.get('keySize', '2048')
        try:
            normalized_key = parse_issue_key_type(
                key_type_in,
                key_size_in,
                curve=data.get('curve'),
            )
        except ValueError as exc:
            return error_response(str(exc), 400)

        EC_CURVES = {
            'prime256v1': ec.SECP256R1(),
            'secp384r1': ec.SECP384R1(),
            'secp521r1': ec.SECP521R1(),
        }
        if normalized_key in EC_CURVES:
            new_key = ec.generate_private_key(EC_CURVES[normalized_key], default_backend())
        else:
            new_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=int(normalized_key),
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

        # Validity (cap 1..3650 days; reject 0/negative/non-int)
        MAX_VALIDITY_DAYS = 3650  # ~10 years; CA/B Forum is 398 for public TLS, 3650 OK for internal PKI
        try:
            validity_days = int(data.get('validity_days', 365))
        except (TypeError, ValueError):
            return error_response("validity_days must be an integer (1..3650)", 400)
        if validity_days < 1 or validity_days > MAX_VALIDITY_DAYS:
            return error_response(
                f"validity_days must be between 1 and {MAX_VALIDITY_DAYS}", 400)
        now = utc_now()
        not_before = cert_not_before()
        not_after = now + timedelta(days=validity_days)

        # Cert validity must not exceed CA cert validity
        ca_not_after = ca_cert.not_valid_after_utc.replace(tzinfo=None)
        if not_after > ca_not_after:
            return error_response(
                f"validity_days exceeds CA expiration ({ca_not_after.isoformat()})", 400)

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
        if data.get('san_upn'):
            from utils.upn_san import build_upn_other_name, is_valid_upn
            for upn in data['san_upn']:
                if not is_valid_upn(upn):
                    return error_response(f'Invalid UPN format: {upn}', 400)
                san_list.append(build_upn_other_name(upn))

        # Auto-add CN as SAN based on cert type
        from utils.san_parse import auto_san_buckets_from_cn

        cn = data['cn']
        implicit = auto_san_buckets_from_cn(
            cn,
            cert_type,
            subject_email=data.get('email'),
        )
        for key in ('san_dns', 'san_ip', 'san_email'):
            existing = set(data.get(key) or [])
            for val in implicit.get(key) or []:
                if val in existing:
                    continue
                if key == 'san_dns' and any(
                    isinstance(s, x509.DNSName) and s.value == val for s in san_list
                ):
                    continue
                if key == 'san_ip' and any(
                    isinstance(s, x509.IPAddress) and str(s.value) == val for s in san_list
                ):
                    continue
                if key == 'san_email' and any(
                    isinstance(s, x509.RFC822Name) and s.value == val for s in san_list
                ):
                    continue
                if key == 'san_dns':
                    san_list.insert(0, x509.DNSName(val))
                elif key == 'san_ip':
                    san_list.insert(0, x509.IPAddress(ip_address(val)))
                elif key == 'san_email':
                    san_list.insert(0, x509.RFC822Name(val))

        # Derive final SAN lists from san_list so auto-added entries are
        # reflected in the DB columns, not just the X.509 extension.
        final_san_dns = [s.value for s in san_list if isinstance(s, x509.DNSName)]
        final_san_ip = [str(s.value) for s in san_list if isinstance(s, x509.IPAddress)]
        final_san_email = [s.value for s in san_list if isinstance(s, x509.RFC822Name)]
        final_san_uri = [s.value for s in san_list if isinstance(s, x509.UniformResourceIdentifier)]
        from utils.upn_san import extract_upns_from_san_list
        final_san_upn = extract_upns_from_san_list(san_list)

        try:
            validate_name_constraints(ca_cert, subject, san_list or None)
        except ValueError as exc:
            logger.info(f"Certificate rejected by CA NameConstraints: {exc}")
            return error_response(str(exc), 400)

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
            cdp_urls = [url.replace('{ca_refid}', ca.url_ref) for url in ca.get_cdp_urls()]
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
                        x509.UniformResourceIdentifier(url.replace('{ca_refid}', ca.url_ref))
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

        # Sign certificate — honor the template digest when one is used
        sign_hash = hashes.SHA256()
        if template and template.digest:
            sign_hash = HASH_ALGORITHMS.get(template.digest.lower().strip(), hashes.SHA256())
        new_cert = builder.sign(ca_key, sign_hash, default_backend())

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
            san_upn=json.dumps(final_san_upn) if final_san_upn else None,
            ocsp_must_staple=bool(data.get('ocsp_must_staple')),
            template_id=template.id if template else None,
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

        # Serialize once, before emitting. The bus fans out to webhook (async),
        # email and WebSocket subscribers, some of which commit the session and
        # thus expire ORM instances — re-reading db_cert afterwards could raise
        # ObjectDeletedError. Reuse this snapshot for the response.
        cert_dict = db_cert.to_dict()
        ca_refid = ca.refid

        # Single lifecycle event — the bus fans out to webhook (async),
        # email and WebSocket subscribers.
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'
        from services.webhook_service import emit_cert_issued
        emit_cert_issued(cert_dict, ca_refid=ca_refid, actor=username)

        return created_response(
            data=cert_dict,
            message='Certificate created successfully'
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create certificate: {e}")
        return error_response('Failed to create certificate', 500)
