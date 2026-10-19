from . import bp, logger, safe_fromstring
from . import saml_sp
from flask import request, Response
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, Certificate
from models.sso import SSOProvider
import urllib.parse
from types import SimpleNamespace
import requests as http_requests
from utils.ssrf_protection import validate_url_not_cloud_metadata
from utils.datetime_utils import utc_now, utc_isoformat
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

    Built with python3-saml from the same settings as the login, so the entity
    ID, ACS URL, signing certificate and AuthnRequestsSigned match what UCM sends.
    """
    from onelogin.saml2.settings import OneLogin_Saml2_Settings

    base = saml_sp.sp_base_url(request)
    endpoints = saml_sp.sp_endpoints(base)
    provider = (SSOProvider.query.filter_by(provider_type='saml', enabled=True).first()
                or SSOProvider.query.filter_by(provider_type='saml').first())
    sign = bool(provider and provider.saml_sign_requests)

    sp_cert = sp_key = None
    try:
        sp_cert, sp_key = saml_sp.load_sp_credentials(provider, with_key=sign)
    except Exception as e:
        logger.warning(f"SAML SP credentials unusable for metadata: {e}")
        try:
            sp_cert, _ = saml_sp.load_sp_credentials(provider)
        except Exception:
            pass
    name_id_format = (provider.saml_name_id_format if provider else None) or saml_sp.NAMEID_UNSPECIFIED

    idp = provider or SimpleNamespace(
        saml_entity_id='https://idp.placeholder.local', saml_sso_url='https://idp.placeholder.local/sso',
        saml_slo_url=None, saml_certificate=None, saml_sign_requests=False, saml_name_id_format=None)
    settings_data = saml_sp.build_settings(idp, base, sp_cert, sp_key)
    # Advertised as configured even if the key is unusable: the login then fails loudly.
    settings_data['security']['authnRequestsSigned'] = sign

    try:
        settings = OneLogin_Saml2_Settings(settings_data, sp_validation_only=True)
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
        cert_body = ''.join(line for line in (sp_cert or '').splitlines() if '-----' not in line)
        key_descriptor = ''
        if cert_body:
            key_descriptor = f'''    <md:KeyDescriptor use="signing">
      <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:X509Data>
          <ds:X509Certificate>{cert_body}</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
'''
        metadata_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     entityID="{endpoints['entity_id']}">
  <md:SPSSODescriptor AuthnRequestsSigned="{'true' if sign else 'false'}"
                      WantAssertionsSigned="false"
                      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
{key_descriptor}    <md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                            Location="{endpoints['slo_url']}"/>
    <md:NameIDFormat>{name_id_format}</md:NameIDFormat>
    <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                                Location="{endpoints['acs_url']}"
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
