"""
OPNsense parser mixin — parses Trust data from OPNsense config.xml.
"""
import base64
import logging
from typing import Dict, List, Optional

import defusedxml.ElementTree as ET
from xml.etree.ElementTree import Element  # noqa: type-only, defusedxml has no Element class
from cryptography import x509
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class ParserMixin:
    """Parses CA and certificate elements from OPNsense config.xml."""

    def parse_trust_data(self, config_xml: str) -> Dict[str, List[Dict]]:
        """
        Parse Trust data from OPNsense config.xml.

        CAs and certificates are stored as direct children of <opnsense> or
        <pfsense> root::

            <opnsense>
                <ca>...</ca>
                <cert>...</cert>
            </opnsense>

        Args:
            config_xml: XML configuration string.

        Returns:
            Dict with 'cas' and 'certs' lists.
        """
        result = {'cas': [], 'certs': []}

        try:
            root = ET.fromstring(config_xml)

            ca_elements = root.findall('ca')
            logger.debug(f"parse_trust_data: Found {len(ca_elements)} CA elements")

            for ca_elem in ca_elements:
                ca_data = self._parse_ca_element(ca_elem)
                if ca_data:
                    result['cas'].append(ca_data)
                    logger.debug(f"parse_trust_data: Parsed CA: {ca_data.get('descr', 'unknown')}")

            cert_elements = root.findall('cert')
            logger.debug(f"parse_trust_data: Found {len(cert_elements)} cert elements")

            for cert_elem in cert_elements:
                cert_data = self._parse_cert_element(cert_elem)
                if cert_data:
                    result['certs'].append(cert_data)
                    logger.debug(f"parse_trust_data: Parsed cert: {cert_data.get('descr', 'unknown')}")

        except Exception as e:
            logger.error(f"Failed to parse config XML: {e}", exc_info=True)

        return result

    def _parse_ca_element(self, ca_elem: Element) -> Optional[Dict]:
        """Parse individual CA element from XML."""
        try:
            ca_data = {}

            for field in ['refid', 'descr', 'crt', 'prv', 'serial']:
                elem = ca_elem.find(field)
                if elem is not None and elem.text:
                    ca_data[field] = elem.text.strip()

            if 'refid' not in ca_data:
                return None

            if 'crt' in ca_data:
                try:
                    cert_pem = base64.b64decode(ca_data['crt'])
                    cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

                    ca_data['subject'] = cert.subject.rfc4514_string()
                    ca_data['issuer'] = cert.issuer.rfc4514_string()
                    ca_data['valid_from'] = cert.not_valid_before
                    ca_data['valid_to'] = cert.not_valid_after
                    ca_data['serial_number'] = str(cert.serial_number)
                    ca_data['is_root'] = (cert.subject == cert.issuer)

                except Exception as e:
                    logger.error(f"Failed to parse CA cert: {e}")

            return ca_data

        except Exception as e:
            logger.error(f"Failed to parse CA element: {e}")
            return None

    def _parse_cert_element(self, cert_elem: Element) -> Optional[Dict]:
        """Parse individual certificate element from XML."""
        try:
            cert_data = {}

            for field in ['refid', 'descr', 'crt', 'prv', 'caref', 'type']:
                elem = cert_elem.find(field)
                if elem is not None and elem.text:
                    cert_data[field] = elem.text.strip()

            if 'refid' not in cert_data:
                return None

            if 'crt' in cert_data:
                try:
                    cert_pem = base64.b64decode(cert_data['crt'])
                    cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

                    cert_data['subject'] = cert.subject.rfc4514_string()
                    cert_data['issuer'] = cert.issuer.rfc4514_string()
                    cert_data['valid_from'] = cert.not_valid_before
                    cert_data['valid_to'] = cert.not_valid_after
                    cert_data['serial_number'] = str(cert.serial_number)

                except Exception as e:
                    logger.error(f"Failed to parse certificate: {e}")

            return cert_data

        except Exception as e:
            logger.error(f"Failed to parse cert element: {e}")
            return None
