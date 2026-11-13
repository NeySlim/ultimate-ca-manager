"""
OPNsense importer mixin — imports parsed CAs and certificates into UCM.
"""
import base64
import json
import logging
import os
import traceback
from pathlib import Path
from typing import Dict, List

from models import db, CA, Certificate
from services.file_regen_service import mirror_private_key
from utils.key_codec import store_pem_bytes
from utils.key_type import weak_ca_key_refusal

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

                if ca_data.get('prv'):
                    weak = weak_ca_key_refusal(base64.b64decode(ca_data['prv']))
                    if weak:
                        raise ValueError(f"'{ca_data.get('descr', refid)}' not imported: {weak}")

                ca = CA(
                    refid=refid,
                    descr=ca_data.get('descr', 'Imported from OPNsense'),
                    crt=ca_data.get('crt', ''),
                    # store_pem_bytes, like the /api/v2/import/opnsense route:
                    # this one assigned the row's base64 PEM straight to the
                    # column, so the same appliance key landed encrypted through
                    # one importer and in the clear through the other.
                    prv=store_pem_bytes(ca_data['prv']) if ca_data.get('prv') else None,
                    caref=None,
                    serial=int(ca_data.get('serial', 0)),
                    subject=ca_data.get('subject', ''),
                    issuer=ca_data.get('issuer', ''),
                    valid_from=ca_data.get('valid_from'),
                    valid_to=ca_data.get('valid_to'),
                    imported_from='opnsense'
                )

                if not ca_data.get('is_root', False):
                    # Chained under the stored CA whose key signed it, never a namesake
                    from cryptography import x509
                    from services.import_service import relink_parent_caref
                    try:
                        ca.caref = relink_parent_caref(
                            x509.load_pem_x509_certificate(base64.b64decode(ca_data.get('crt') or '')), None)
                    except ValueError:
                        ca.caref = None

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
                        mirror_private_key(
                            Path(key_file),
                            base64.b64decode(ca_data['prv']),
                            context=f"OPNsense CA {ca.id}",
                        )

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

        created = []
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
                    # The entry's caref is only a claim: linked to the CA whose key signed it
                    try:
                        from utils.cert_issuer import ca_signed, signing_ca_for
                        leaf = x509.load_pem_x509_certificate(base64.b64decode(cert_data.get('crt') or ''))
                        signer = ca if ca_signed(ca, leaf) else signing_ca_for(leaf)
                        caref = signer.refid if signer else None
                    except Exception:
                        caref = None

                serial = cert_data.get('serial_number', '')
                if Certificate.stored_under(caref, serial):  # uix_certificates_ca_serial
                    stats['skipped'] += 1
                    stats['errors'].append(f"Cert {refid}: serial {serial} {Certificate.DUPLICATE_SERIAL}")
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
                    prv=store_pem_bytes(cert_data['prv']) if cert_data.get('prv') else None,
                    cert_type=cert_data.get('type', 'server_cert'),
                    subject=cert_data.get('subject', ''),
                    issuer=cert_data.get('issuer', ''),
                    serial_number=serial,
                    valid_from=cert_data.get('valid_from'),
                    valid_to=cert_data.get('valid_to'),
                    san_dns=json.dumps(san_dns_list) if san_dns_list else None,
                    san_ip=json.dumps(san_ip_list) if san_ip_list else None,
                    san_email=json.dumps(san_email_list) if san_email_list else None,
                    san_uri=json.dumps(san_uri_list) if san_uri_list else None,
                    imported_from='opnsense',
                    created_by='import'
                )
                from services.cert.issued_lookup import apply_persisted_revocation
                apply_persisted_revocation(cert)

                db.session.add(cert)
                db.session.flush()
                created.append(cert)

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
                        mirror_private_key(
                            Path(key_file),
                            base64.b64decode(cert_data['prv']),
                            context=f"OPNsense certificate {cert.id}",
                        )

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

        from services.webhook_service import emit_cert_imported
        for cert in created:
            emit_cert_imported(cert.to_dict(), ca_refid=cert.caref)
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
