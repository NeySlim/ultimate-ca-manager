from . import bp, logger
from flask import request, Response
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, Certificate
from models.sso import SSOProvider
import base64
import urllib.parse
import requests as http_requests
from utils.ssrf_protection import validate_url_not_cloud_metadata
from services.audit_service import AuditService

@bp.route('/api/v2/sso/saml/certificates', methods=['GET'])
@require_auth(['read:sso'])
def list_saml_certificates():
    """List valid certificates available for SAML SP metadata.
    Returns HTTPS cert + all valid certs from the database."""
    import os
    from datetime import datetime

    certs = []

    # Option 1: HTTPS certificate (default)
    data_path = os.environ.get('DATA_PATH', '/opt/ucm/data')
    cert_path = os.path.join(data_path, 'https_cert.pem')
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        with open(cert_path, 'rb') as f:
            pem_data = f.read()
        cert = x509.load_pem_x509_certificate(pem_data)
        certs.append({
            'id': 'https',
            'label': f'HTTPS Certificate ({cert.subject.rfc4514_string()})',
            'subject': cert.subject.rfc4514_string(),
            'not_after': utc_isoformat(cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after),
            'is_default': True,
        })
    except Exception as e:
        logger.warning(f"Could not load HTTPS cert: {e}")
        certs.append({
            'id': 'https',
            'label': 'HTTPS Certificate',
            'subject': 'Unknown',
            'not_after': None,
            'is_default': True,
        })

    # Option 2+: Valid certificates from database
    try:
        db_certs = Certificate.query.filter(
            Certificate.revoked == False,
            Certificate.valid_to > utc_now(),
            Certificate.crt.isnot(None)
        ).order_by(Certificate.subject_cn).all()

        for c in db_certs:
            certs.append({
                'id': str(c.id),
                'label': c.subject_cn or c.descr or f'Certificate #{c.id}',
                'subject': c.subject,
                'issuer': c.issuer,
                'not_after': utc_isoformat(c.valid_to),
                'key_type': c.key_algo,
                'is_default': False,
            })
    except Exception as e:
        logger.warning(f"Could not list certificates: {e}")

    return success_response(data=certs)


@bp.route('/api/v2/sso/saml/metadata', methods=['GET'])
def get_sp_metadata():
    """Generate schema-valid SAML 2.0 SP metadata XML for configuring the IDP.

    Uses python3-saml's metadata builder to ensure compliance with
    the SAML 2.0 Metadata XSD (correct element ordering, validUntil, etc.).
    Includes SP signing certificate (HTTPS cert) in KeyDescriptor.
    Works with strict IDPs like Omnissa Workspace ONE Access, ADFS, Shibboleth.
    """
    import os
    from onelogin.saml2.settings import OneLogin_Saml2_Settings

    sp_base = request.url_root.rstrip('/')
    entity_id = f'{sp_base}/api/v2/sso'
    acs_url = f'{sp_base}/api/v2/sso/callback/saml'
    slo_url = f'{sp_base}/api/v2/sso/callback/saml'

    # Load SAML provider config if available (for NameIDFormat override + cert source)
    provider = SSOProvider.query.filter_by(provider_type='saml').first()
    name_id_format = (getattr(provider, 'saml_name_id_format', None)
                      if provider else None) or 'urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified'

    # Determine certificate source
    cert_source = (getattr(provider, 'saml_sp_cert_source', None)
                   if provider else None) or 'https'

    # Load SP certificate for KeyDescriptor
    sp_cert = ''
    data_path = os.environ.get('DATA_PATH', '/opt/ucm/data')

    if cert_source != 'https':
        # Load certificate from database by ID (must be valid and not revoked)
        try:
            from datetime import datetime as dt
            db_cert = Certificate.query.filter(
                Certificate.id == int(cert_source),
                Certificate.revoked == False,
                Certificate.valid_to > utc_now(),
                Certificate.crt.isnot(None)
            ).first()
            if db_cert:
                cert_content = base64.b64decode(db_cert.crt).decode('utf-8')
                in_cert = False
                cert_lines = []
                for line in cert_content.splitlines():
                    if '-----BEGIN CERTIFICATE-----' in line:
                        in_cert = True
                        continue
                    if '-----END CERTIFICATE-----' in line:
                        break
                    if in_cert:
                        cert_lines.append(line.strip())
                sp_cert = ''.join(cert_lines)
                logger.info(f"Using database certificate #{cert_source} for SP metadata")
            else:
                logger.warning(f"Certificate #{cert_source} not found, falling back to HTTPS cert")
                cert_source = 'https'
        except Exception as e:
            logger.warning(f"Could not load certificate #{cert_source}: {e}, falling back to HTTPS cert")
            cert_source = 'https'

    if cert_source == 'https':
        # Default: use HTTPS certificate
        cert_path = os.path.join(data_path, 'https_cert.pem')
        try:
            with open(cert_path, 'r') as f:
                cert_content = f.read()
            in_cert = False
            cert_lines = []
            for line in cert_content.splitlines():
                if '-----BEGIN CERTIFICATE-----' in line:
                    in_cert = True
                    continue
                if '-----END CERTIFICATE-----' in line:
                    break
                if in_cert:
                    cert_lines.append(line.strip())
            sp_cert = ''.join(cert_lines)
        except Exception as e:
            logger.warning(f"Could not load SP certificate from {cert_path}: {e}")

    settings_data = {
        'strict': False,
        'sp': {
            'entityId': entity_id,
            'assertionConsumerService': {
                'url': acs_url,
                'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST',
            },
            'singleLogoutService': {
                'url': slo_url,
                'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
            },
            'NameIDFormat': name_id_format,
        },
        'idp': {
            'entityId': 'https://idp.placeholder.local',
            'singleSignOnService': {
                'url': 'https://idp.placeholder.local/sso',
                'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
            },
        },
    }

    # Include SP cert if available — generates KeyDescriptor in metadata
    if sp_cert:
        settings_data['sp']['x509cert'] = sp_cert

    try:
        settings = OneLogin_Saml2_Settings(settings_data, custom_base_path='/tmp')
        metadata = settings.get_sp_metadata()
        if isinstance(metadata, bytes):
            metadata = metadata.decode('utf-8')

        errors = settings.validate_metadata(metadata)
        if errors:
            logger.warning(f"SP metadata validation warnings: {errors}")

        return Response(metadata, mimetype='application/xml',
                        headers={'Content-Disposition': 'inline; filename="ucm-sp-metadata.xml"'})
    except Exception as e:
        logger.error(f"Failed to generate SP metadata via python3-saml: {e}")
        # Fallback: hand-crafted but schema-compliant (correct element order per XSD)
        key_descriptor = ''
        if sp_cert:
            key_descriptor = f'''    <md:KeyDescriptor use="signing">
      <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:X509Data>
          <ds:X509Certificate>{sp_cert}</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
'''
        metadata_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     entityID="{entity_id}">
  <md:SPSSODescriptor AuthnRequestsSigned="false"
                      WantAssertionsSigned="true"
                      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
{key_descriptor}    <md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                            Location="{slo_url}"/>
    <md:NameIDFormat>{name_id_format}</md:NameIDFormat>
    <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                                Location="{acs_url}"
                                index="1"
                                isDefault="true"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>'''
        return Response(metadata_xml, mimetype='application/xml',
                        headers={'Content-Disposition': 'inline; filename="ucm-sp-metadata.xml"'})


def _parse_saml_metadata(xml_text):
    """Parse SAML IDP metadata XML and extract key fields"""
    NS = {
        'md': 'urn:oasis:names:tc:SAML:2.0:metadata',
        'ds': 'http://www.w3.org/2000/09/xmldsig#',
    }

    root = safe_fromstring(xml_text.encode('utf-8'))

    result = {
        'entity_id': None,
        'sso_url': None,
        'slo_url': None,
        'certificate': None,
    }

    # Entity ID from root or IDPSSODescriptor
    result['entity_id'] = root.get('entityID')

    # Find IDPSSODescriptor
    idp = root.find('.//md:IDPSSODescriptor', NS)
    if idp is None:
        # Try without namespace prefix (some IdPs use default ns)
        idp = root.find('.//{urn:oasis:names:tc:SAML:2.0:metadata}IDPSSODescriptor')

    if idp is not None:
        # SSO URL (HTTP-Redirect preferred, fallback to HTTP-POST)
        for binding in ['urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
                        'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST']:
            sso = idp.find(f'md:SingleSignOnService[@Binding="{binding}"]', NS)
            if sso is None:
                sso = idp.find(f'{{urn:oasis:names:tc:SAML:2.0:metadata}}SingleSignOnService[@Binding="{binding}"]')
            if sso is not None:
                result['sso_url'] = sso.get('Location')
                break

        # SLO URL
        for binding in ['urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
                        'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST']:
            slo = idp.find(f'md:SingleLogoutService[@Binding="{binding}"]', NS)
            if slo is None:
                slo = idp.find(f'{{urn:oasis:names:tc:SAML:2.0:metadata}}SingleLogoutService[@Binding="{binding}"]')
            if slo is not None:
                result['slo_url'] = slo.get('Location')
                break

        # Certificate (first X509Certificate found)
        cert = idp.find('.//ds:X509Certificate', NS)
        if cert is None:
            cert = idp.find('.//{http://www.w3.org/2000/09/xmldsig#}X509Certificate')
        if cert is not None and cert.text:
            # Clean up whitespace and format
            cert_text = cert.text.strip().replace('\n', '').replace(' ', '')
            # Format as PEM lines of 64 chars
            lines = [cert_text[i:i+64] for i in range(0, len(cert_text), 64)]
            result['certificate'] = '\n'.join(lines)

    if not result['entity_id'] and not result['sso_url']:
        raise ValueError("Could not find IDP entity ID or SSO URL in metadata")

    return result
