"""
OPNsense importer mixin — imports parsed CAs and certificates into UCM.
"""
import base64
import json
import logging
import os
import traceback
from typing import Dict, List

from models import db, CA, Certificate

logger = logging.getLogger(__name__)


class ImportMixin:
    """Imports parsed OPNsense Trust data into the UCM database."""

    def import_cas(self, cas_data: List[Dict], skip_existing: bool = True) -> Dict:
        """
        Import CAs into UCM database.

        Args:
            cas_data: List of CA data dictionaries.
            skip_existing: Skip if CA with same refid already exists.

        Returns:
            Dict with import statistics.
        """
        stats = {
            'total': len(cas_data),
            'imported': 0,
            'skipped': 0,
            'failed': 0,
            'errors': []
        }

        # Sort CAs: root CAs first, then intermediates
        root_cas = [ca for ca in cas_data if ca.get('is_root', False)]
        intermediate_cas = [ca for ca in cas_data if not ca.get('is_root', False)]
        sorted_cas = root_cas + intermediate_cas

        for ca_data in sorted_cas:
            try:
                refid = ca_data['refid']

                if skip_existing:
                    existing = CA.query.filter_by(refid=refid).first()
                    if existing:
                        stats['skipped'] += 1
                        continue

                ca = CA(
                    refid=refid,
                    descr=ca_data.get('descr', 'Imported from OPNsense'),
                    crt=ca_data.get('crt', ''),
                    prv=ca_data.get('prv'),
                    caref=None,
                    serial=int(ca_data.get('serial', 0)),
                    subject=ca_data.get('subject', ''),
                    issuer=ca_data.get('issuer', ''),
                    valid_from=ca_data.get('valid_from'),
                    valid_to=ca_data.get('valid_to'),
                    imported_from='opnsense'
                )

                if not ca_data.get('is_root', False):
                    issuer = ca_data.get('issuer', '')
                    parent_ca = CA.query.filter_by(subject=issuer).first()
                    if parent_ca:
                        ca.caref = parent_ca.refid

                db.session.add(ca)
                db.session.flush()

                if ca_data.get('crt'):
                    data_dir = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"
                    )
                    ca_dir = os.path.join(data_dir, "ca")
                    os.makedirs(ca_dir, exist_ok=True)

                    ca_file = os.path.join(ca_dir, f"{refid}.crt")
                    with open(ca_file, "wb") as f:
                        f.write(base64.b64decode(ca_data['crt']))

                    if ca_data.get('prv'):
                        private_dir = os.path.join(data_dir, "private")
                        os.makedirs(private_dir, exist_ok=True)

                        key_file = os.path.join(private_dir, f"{refid}.key")
                        with open(key_file, "wb") as f:
                            f.write(base64.b64decode(ca_data['prv']))
                        os.chmod(key_file, 0o600)

                stats['imported'] += 1

            except Exception as e:
                stats['failed'] += 1
                stats['errors'].append(f"CA {ca_data.get('refid', 'unknown')}: {e}")
                logger.error(f"Failed to import CA: {e}")
                traceback.print_exc()

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            stats['errors'].append(f"Database commit failed: {e}")

        return stats

    def import_certificates(self, certs_data: List[Dict], skip_existing: bool = True) -> Dict:
        """
        Import certificates into UCM database.

        Args:
            certs_data: List of certificate data dictionaries.
            skip_existing: Skip if cert with same refid already exists.

        Returns:
            Dict with import statistics.
        """
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend

        stats = {
            'total': len(certs_data),
            'imported': 0,
            'skipped': 0,
            'failed': 0,
            'errors': []
        }

        for cert_data in certs_data:
            try:
                refid = cert_data['refid']

                if skip_existing:
                    existing = Certificate.query.filter_by(refid=refid).first()
                    if existing:
                        stats['skipped'] += 1
                        continue

                caref = cert_data.get('caref')
                if caref:
                    ca = CA.query.filter_by(refid=caref).first()
                    if not ca:
                        stats['failed'] += 1
                        stats['errors'].append(f"Cert {refid}: CA {caref} not found")
                        continue

                san_dns_list = []
                san_ip_list = []
                san_email_list = []
                san_uri_list = []

                if cert_data.get('crt'):
                    try:
                        cert_pem = base64.b64decode(cert_data['crt'])
                        x509_cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

                        try:
                            ext = x509_cert.extensions.get_extension_for_oid(
                                x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                            )
                            for name in ext.value:
                                if isinstance(name, x509.DNSName):
                                    san_dns_list.append(name.value)
                                elif isinstance(name, x509.IPAddress):
                                    san_ip_list.append(str(name.value))
                                elif isinstance(name, x509.RFC822Name):
                                    san_email_list.append(name.value)
                                elif isinstance(name, x509.UniformResourceIdentifier):
                                    san_uri_list.append(name.value)
                        except x509.ExtensionNotFound:
                            pass
                    except Exception:
                        pass

                cert = Certificate(
                    refid=refid,
                    caref=caref,
                    descr=cert_data.get('descr', 'Imported from OPNsense'),
                    crt=cert_data.get('crt', ''),
                    prv=cert_data.get('prv'),
                    cert_type=cert_data.get('type', 'server_cert'),
                    subject=cert_data.get('subject', ''),
                    issuer=cert_data.get('issuer', ''),
                    serial_number=cert_data.get('serial_number', ''),
                    valid_from=cert_data.get('valid_from'),
                    valid_to=cert_data.get('valid_to'),
                    san_dns=json.dumps(san_dns_list) if san_dns_list else None,
                    san_ip=json.dumps(san_ip_list) if san_ip_list else None,
                    san_email=json.dumps(san_email_list) if san_email_list else None,
                    san_uri=json.dumps(san_uri_list) if san_uri_list else None,
                    imported_from='opnsense',
                    created_by='import'
                )

                db.session.add(cert)
                db.session.flush()

                if cert_data.get('crt'):
                    data_dir = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"
                    )
                    certs_dir = os.path.join(data_dir, "certs")
                    os.makedirs(certs_dir, exist_ok=True)

                    cert_file = os.path.join(certs_dir, f"{refid}.crt")
                    with open(cert_file, "wb") as f:
                        f.write(base64.b64decode(cert_data['crt']))

                    if cert_data.get('prv'):
                        private_dir = os.path.join(data_dir, "private")
                        os.makedirs(private_dir, exist_ok=True)

                        key_file = os.path.join(private_dir, f"{refid}.key")
                        with open(key_file, "wb") as f:
                            f.write(base64.b64decode(cert_data['prv']))
                        os.chmod(key_file, 0o600)

                stats['imported'] += 1

            except Exception as e:
                stats['failed'] += 1
                stats['errors'].append(f"Cert {cert_data.get('refid', 'unknown')}: {e}")
                logger.error(f"Failed to import certificate: {e}")
                traceback.print_exc()

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            stats['errors'].append(f"Database commit failed: {e}")

        return stats

    def full_import(self, skip_existing: bool = True) -> Dict:
        """
        Perform full import of CAs and certificates.

        Args:
            skip_existing: Skip items that already exist.

        Returns:
            Dict with complete import statistics.
        """
        result = {
            'success': False,
            'connected': False,
            'config_retrieved': False,
            'cas': None,
            'certs': None,
            'errors': []
        }

        if not self.connect():
            result['errors'].append("Failed to connect to OPNsense")
            logger.error("full_import: Connection failed")
            return result

        result['connected'] = True
        logger.debug("full_import: Connected successfully")

        config_xml = self.get_config_xml()
        if not config_xml:
            result['errors'].append("Failed to retrieve config.xml")
            logger.error("full_import: Failed to get config.xml")
            return result

        result['config_retrieved'] = True
        logger.debug(f"full_import: Config retrieved ({len(config_xml)} bytes)")

        try:
            data = self.parse_trust_data(config_xml)
            logger.debug(f"full_import: Parsed {len(data['cas'])} CAs, {len(data['certs'])} certs")
        except Exception as e:
            result['errors'].append(f"Failed to parse config.xml: {e}")
            logger.error(f"full_import: Parse failed: {e}", exc_info=True)
            return result

        try:
            result['cas'] = self.import_cas(data['cas'], skip_existing)
            logger.debug(f"full_import: CA import result: {result['cas']}")
        except Exception as e:
            result['errors'].append(f"Failed to import CAs: {e}")
            logger.error(f"full_import: CA import failed: {e}", exc_info=True)
            result['cas'] = {'imported': 0, 'skipped': 0, 'errors': [str(e)]}

        try:
            result['certs'] = self.import_certificates(data['certs'], skip_existing)
            logger.debug(f"full_import: Cert import result: {result['certs']}")
        except Exception as e:
            result['errors'].append(f"Failed to import certificates: {e}")
            logger.error(f"full_import: Cert import failed: {e}", exc_info=True)
            result['certs'] = {'imported': 0, 'skipped': 0, 'errors': [str(e)]}

        if result['cas'] and result['certs']:
            total_imported = result['cas']['imported'] + result['certs']['imported']
            total_processed = (
                total_imported
                + result['cas']['skipped']
                + result['certs']['skipped']
            )
            result['success'] = True
            logger.debug(
                f"full_import: SUCCESS - Imported: {total_imported}, "
                f"Skipped: {total_processed - total_imported}"
            )

        return result
