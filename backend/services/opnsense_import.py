"""
OPNsense Import Service
Generic service to import CAs and Certificates from OPNsense Trust module
Configurable via API for any OPNsense instance
"""
import base64
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from models import db, CA, Certificate, SystemConfig
from utils.safe_requests import create_session


class OPNsenseImportService:
    """Service for importing Trust data from OPNsense"""
    
    def __init__(self, base_url: str, username: str = None, password: str = None, 
                 api_key: str = None, api_secret: str = None,
                 verify_ssl: bool = False):
        """
        Initialize OPNsense import service
        
        Supports two authentication methods:
        1. Username/Password (legacy web scraping method)
        2. API Key/Secret (REST API method - recommended)
        
        Args:
            base_url: OPNsense base URL (e.g., https://192.168.1.1)
            username: OPNsense username (for web scraping auth)
            password: OPNsense password (for web scraping auth)
            api_key: OPNsense API key (for REST API auth - recommended)
            api_secret: OPNsense API secret (for REST API auth - recommended)
            verify_ssl: Verify SSL certificate (default False for self-signed)
        """
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.api_key = api_key
        self.api_secret = api_secret
        self.verify_ssl = verify_ssl
        self.session = None
        
        # Determine which auth method to use
        self.use_api = bool(api_key and api_secret)
        
        if not self.use_api and not (username and password):
            raise ValueError("Must provide either username/password or api_key/api_secret")
        
    def connect(self) -> bool:
        """
        Test connection to OPNsense instance
        
        Returns:
            True if connection successful
        """
        import sys
        try:
            self.session = create_session(verify_ssl=self.verify_ssl)
            
            sys.stderr.write(f"DEBUG OPNsense connect: Trying {self.base_url} (API mode: {self.use_api})\n")
            sys.stderr.flush()
            
            if self.use_api:
                # Test REST API connection
                response = self.session.get(
                    f"{self.base_url}/api/core/backup/providers",
                    auth=(self.api_key, self.api_secret),
                    timeout=10
                )
                
                sys.stderr.write(f"DEBUG OPNsense API test: Got status {response.status_code}\n")
                sys.stderr.flush()
                
                return response.status_code == 200
            else:
                # Test web interface connection
                response = self.session.get(
                    f"{self.base_url}/",
                    auth=(self.username, self.password),
                    timeout=10
                )
                
                sys.stderr.write(f"DEBUG OPNsense web test: Got status {response.status_code}\n")
                sys.stderr.flush()
                
                return response.status_code == 200
        
        except Exception as e:
            sys.stderr.write(f"ERROR OPNsense connect failed: {type(e).__name__}: {str(e)}\n")
            sys.stderr.flush()
            return False
    
    def get_config_xml(self) -> Optional[str]:
        """
        Retrieve OPNsense config.xml
        
        Uses REST API if api_key/secret provided (recommended),
        otherwise falls back to web scraping with CSRF handling
        
        Returns:
            XML string or None if failed
        """
        import sys
        import re
        
        # Use REST API if available
        if self.use_api:
            return self._get_config_xml_api()
        else:
            return self._get_config_xml_web()
    
    def _get_config_xml_api(self) -> Optional[str]:
        """
        Retrieve config.xml using REST API
        Endpoint: GET /api/core/backup/download/this
        
        Returns:
            XML string or None if failed
        """
        import sys
        
        try:
            sys.stderr.write(f"DEBUG get_config_xml_api: Downloading via REST API...\n")
            sys.stderr.flush()
            
            response = self.session.get(
                f"{self.base_url}/api/core/backup/download/this",
                auth=(self.api_key, self.api_secret),
                timeout=60
            )
            
            sys.stderr.write(f"DEBUG get_config_xml_api: Status {response.status_code}, Size: {len(response.content)} bytes\n")
            sys.stderr.flush()
            
            if response.status_code == 200:
                content = response.text
                
                # Verify it's XML
                if '<?xml' in content[:100]:
                    if '<opnsense>' in content or '<pfsense>' in content:
                        sys.stderr.write(f"DEBUG get_config_xml_api: Successfully retrieved config.xml via REST API\n")
                        sys.stderr.flush()
                        return content
                    else:
                        sys.stderr.write(f"ERROR get_config_xml_api: XML found but not OPNsense format\n")
                        sys.stderr.flush()
                else:
                    sys.stderr.write(f"ERROR get_config_xml_api: Response is not XML\n")
                    sys.stderr.write(f"DEBUG Content starts with: {content[:200]}\n")
                    sys.stderr.flush()
            else:
                sys.stderr.write(f"ERROR get_config_xml_api: Request failed with status {response.status_code}\n")
                if response.status_code == 401:
                    sys.stderr.write(f"ERROR Authentication failed - check API key/secret\n")
                sys.stderr.flush()
            
            return None
            
        except Exception as e:
            sys.stderr.write(f"ERROR get_config_xml_api failed: {type(e).__name__}: {str(e)}\n")
            sys.stderr.flush()
            return None
    
    def _get_config_xml_web(self) -> Optional[str]:
        """
        Retrieve OPNsense config.xml with web scraping and CSRF handling
        OPNsense uses X-CSRFToken header instead of form fields
        
        Returns:
            XML string or None if failed
        """
        import sys
        import re
        
        try:
            # Step 1: GET login page to obtain CSRF token
            sys.stderr.write(f"DEBUG get_config_xml: Step 1 - Getting login page for CSRF token...\n")
            sys.stderr.flush()
            
            login_page_response = self.session.get(
                f"{self.base_url}/",
                timeout=30
            )
            
            if login_page_response.status_code != 200:
                sys.stderr.write(f"ERROR get_config_xml: Failed to get login page: {login_page_response.status_code}\n")
                sys.stderr.flush()
                return None
            
            # Extract CSRF token from JavaScript
            # OPNsense embeds it in: xhr.setRequestHeader("X-CSRFToken", "TOKEN_HERE");
            csrf_pattern = r'X-CSRFToken["\']\s*,\s*["\']([^"\']+)["\']'
            csrf_match = re.search(csrf_pattern, login_page_response.text)
            
            if not csrf_match:
                sys.stderr.write(f"ERROR get_config_xml: Could not find X-CSRFToken in page\n")
                sys.stderr.write(f"DEBUG Searching in: {login_page_response.text[:1000]}\n")
                sys.stderr.flush()
                return None
            
            csrf_token = csrf_match.group(1)
            sys.stderr.write(f"DEBUG get_config_xml: Found X-CSRFToken: {csrf_token}\n")
            sys.stderr.flush()
            
            # Step 2: POST login with X-CSRFToken header
            sys.stderr.write(f"DEBUG get_config_xml: Step 2 - Logging in with X-CSRFToken header...\n")
            sys.stderr.flush()
            
            login_response = self.session.post(
                f"{self.base_url}/",
                data={
                    'usernamefld': self.username,
                    'passwordfld': self.password,
                    'login': 'Login'
                },
                headers={
                    'X-CSRFToken': csrf_token
                },
                timeout=30,
                allow_redirects=True
            )
            
            sys.stderr.write(f"DEBUG get_config_xml: Login response status: {login_response.status_code}\n")
            sys.stderr.flush()
            
            if login_response.status_code == 403:
                sys.stderr.write(f"ERROR get_config_xml: Login failed - 403 Forbidden\n")
                sys.stderr.flush()
                return None
            
            # Step 3: GET backup page to obtain new CSRF token
            sys.stderr.write(f"DEBUG get_config_xml: Step 3 - Getting backup page for new CSRF token...\n")
            sys.stderr.flush()
            
            backup_page_response = self.session.get(
                f"{self.base_url}/diag_backup.php",
                timeout=30
            )
            
            if backup_page_response.status_code != 200:
                sys.stderr.write(f"ERROR get_config_xml: Failed to get backup page: {backup_page_response.status_code}\n")
                sys.stderr.flush()
                return None
            
            # Extract new CSRF token from backup page
            csrf_match = re.search(csrf_pattern, backup_page_response.text)
            
            if not csrf_match:
                sys.stderr.write(f"WARNING get_config_xml: Could not find new CSRF token, reusing old one\n")
                sys.stderr.flush()
            else:
                csrf_token = csrf_match.group(1)
                sys.stderr.write(f"DEBUG get_config_xml: Found new X-CSRFToken: {csrf_token}\n")
                sys.stderr.flush()
            
            # Step 4: POST download request with X-CSRFToken header
            sys.stderr.write(f"DEBUG get_config_xml: Step 4 - Downloading config with X-CSRFToken header...\n")
            sys.stderr.flush()
            
            # Try different download methods
            backup_response = self.session.post(
                f"{self.base_url}/diag_backup.php",
                data={
                    'download': 'download',
                    'donotbackuprrd': 'yes'
                },
                headers={
                    'X-CSRFToken': csrf_token
                },
                timeout=60
            )
            
            sys.stderr.write(f"DEBUG get_config_xml: Backup download status: {backup_response.status_code}\n")
            sys.stderr.write(f"DEBUG get_config_xml: Content length: {len(backup_response.content)}\n")
            sys.stderr.flush()
            
            # If first attempt returns HTML, try alternative method
            if backup_response.status_code == 200 and '<!doctype html>' in backup_response.text.lower()[:100]:
                sys.stderr.write(f"DEBUG get_config_xml: First attempt returned HTML, trying alternative method...\n")
                sys.stderr.flush()
                
                # Try method 2: using 'backup' as action
                backup_response = self.session.post(
                    f"{self.base_url}/diag_backup.php",
                    data={
                        'action': 'download',
                        'donotbackuprrd': '1'
                    },
                    headers={
                        'X-CSRFToken': csrf_token
                    },
                    timeout=60
                )
                
                sys.stderr.write(f"DEBUG get_config_xml: Alternative method status: {backup_response.status_code}\n")
                sys.stderr.flush()
            
            # If still HTML, try method 3: GET with query params
            if backup_response.status_code == 200 and '<!doctype html>' in backup_response.text.lower()[:100]:
                sys.stderr.write(f"DEBUG get_config_xml: Still HTML, trying GET method...\n")
                sys.stderr.flush()
                
                backup_response = self.session.get(
                    f"{self.base_url}/diag_backup.php?download=download&donotbackuprrd=yes",
                    headers={
                        'X-CSRFToken': csrf_token
                    },
                    timeout=60
                )
                
                sys.stderr.write(f"DEBUG get_config_xml: GET method status: {backup_response.status_code}\n")
                sys.stderr.flush()
            
            if backup_response.status_code == 200:
                # Check if it's XML (could be gzipped)
                content = backup_response.text
                
                # Check for XML markers
                if '<?xml' in content[:100]:
                    sys.stderr.write(f"DEBUG get_config_xml: Valid XML found!\n")
                    sys.stderr.flush()
                    
                    # Verify it's OPNsense config
                    if '<opnsense>' in content or '<pfsense>' in content:
                        sys.stderr.write(f"DEBUG get_config_xml: OPNsense/pfSense config confirmed! Size: {len(content)} bytes\n")
                        sys.stderr.flush()
                        return content
                    else:
                        sys.stderr.write(f"WARNING get_config_xml: XML found but not OPNsense/pfSense format\n")
                        sys.stderr.flush()
                else:
                    sys.stderr.write(f"ERROR get_config_xml: Response is not XML\n")
                    sys.stderr.write(f"DEBUG Content starts with: {content[:200]}\n")
                    sys.stderr.flush()
            else:
                sys.stderr.write(f"ERROR get_config_xml: Backup download failed with status {backup_response.status_code}\n")
                sys.stderr.flush()
            
            return None
            
        except Exception as e:
            sys.stderr.write(f"ERROR get_config_xml: Exception occurred: {type(e).__name__}: {str(e)}\n")
            sys.stderr.flush()
            import traceback
            sys.stderr.write(f"Traceback:\n{traceback.format_exc()}\n")
            sys.stderr.flush()
            return None
            
            sys.stderr.write(f"ERROR get_config_xml: Could not retrieve config.xml via standard methods\n")
            sys.stderr.flush()
            print("Could not retrieve config.xml via standard methods")
            print("You may need to:")
            print("  1. Download config.xml manually from OPNsense")
            print("  2. Use the /import/upload endpoint to import it")
            
            return None
        
        except Exception as e:
            print(f"Failed to get config.xml: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def parse_trust_data(self, config_xml: str) -> Dict[str, List[Dict]]:
        """
        Parse Trust data from OPNsense config.xml
        
        CAs and certificates are stored as direct children of <opnsense> or <pfsense> root:
        <opnsense>
            <ca>...</ca>
            <ca>...</ca>
            <cert>...</cert>
            <cert>...</cert>
        </opnsense>
        
        Args:
            config_xml: XML configuration string
            
        Returns:
            Dict with 'cas' and 'certs' lists
        """
        import sys
        result = {
            'cas': [],
            'certs': []
        }
        
        try:
            root = ET.fromstring(config_xml)
            
            # Find all CA elements (direct children of root)
            ca_elements = root.findall('ca')
            sys.stderr.write(f"DEBUG parse_trust_data: Found {len(ca_elements)} CA elements\n")
            sys.stderr.flush()
            
            for ca_elem in ca_elements:
                ca_data = self._parse_ca_element(ca_elem)
                if ca_data:
                    result['cas'].append(ca_data)
                    sys.stderr.write(f"DEBUG parse_trust_data: Parsed CA: {ca_data.get('descr', 'unknown')}\n")
                    sys.stderr.flush()
            
            # Find all certificate elements (direct children of root)
            cert_elements = root.findall('cert')
            sys.stderr.write(f"DEBUG parse_trust_data: Found {len(cert_elements)} cert elements\n")
            sys.stderr.flush()
            
            for cert_elem in cert_elements:
                cert_data = self._parse_cert_element(cert_elem)
                if cert_data:
                    result['certs'].append(cert_data)
                    sys.stderr.write(f"DEBUG parse_trust_data: Parsed cert: {cert_data.get('descr', 'unknown')}\n")
                    sys.stderr.flush()
        
        except Exception as e:
            sys.stderr.write(f"ERROR Failed to parse config XML: {e}\n")
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
        
        return result
    
    def _parse_ca_element(self, ca_elem: ET.Element) -> Optional[Dict]:
        """Parse individual CA element from XML"""
        try:
            ca_data = {}
            
            # Get basic fields
            for field in ['refid', 'descr', 'crt', 'prv', 'serial']:
                elem = ca_elem.find(field)
                if elem is not None and elem.text:
                    ca_data[field] = elem.text.strip()
            
            # refid is required
            if 'refid' not in ca_data:
                return None
            
            # Parse certificate to get subject/issuer
            if 'crt' in ca_data:
                try:
                    # OPNsense stores in base64
                    cert_pem = base64.b64decode(ca_data['crt'])
                    cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
                    
                    ca_data['subject'] = cert.subject.rfc4514_string()
                    ca_data['issuer'] = cert.issuer.rfc4514_string()
                    ca_data['valid_from'] = cert.not_valid_before
                    ca_data['valid_to'] = cert.not_valid_after
                    ca_data['serial_number'] = str(cert.serial_number)
                    
                    # Check if it's a root CA (self-signed)
                    ca_data['is_root'] = (cert.subject == cert.issuer)
                
                except Exception as e:
                    print(f"Failed to parse CA cert: {e}")
            
            return ca_data
        
        except Exception as e:
            print(f"Failed to parse CA element: {e}")
            return None
    
    def _parse_cert_element(self, cert_elem: ET.Element) -> Optional[Dict]:
        """Parse individual certificate element from XML"""
        try:
            cert_data = {}
            
            # Get basic fields
            for field in ['refid', 'descr', 'crt', 'prv', 'caref', 'type']:
                elem = cert_elem.find(field)
                if elem is not None and elem.text:
                    cert_data[field] = elem.text.strip()
            
            # refid is required
            if 'refid' not in cert_data:
                return None
            
            # Parse certificate
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
                    print(f"Failed to parse certificate: {e}")
            
            return cert_data
        
        except Exception as e:
            print(f"Failed to parse cert element: {e}")
            return None
    
    def import_cas(self, cas_data: List[Dict], skip_existing: bool = True) -> Dict:
        """
        Import CAs into UCM database
        
        Args:
            cas_data: List of CA data dictionaries
            skip_existing: Skip if CA with same refid already exists
            
        Returns:
            Dict with import statistics
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
                
                # Check if already exists
                if skip_existing:
                    existing = CA.query.filter_by(refid=refid).first()
                    if existing:
                        stats['skipped'] += 1
                        continue
                
                # Create CA record
                ca = CA(
                    refid=refid,
                    descr=ca_data.get('descr', 'Imported from OPNsense'),
                    crt=ca_data.get('crt', ''),
                    prv=ca_data.get('prv'),  # May be None for imported CAs
                    caref=None,  # Will be set for intermediates
                    serial=int(ca_data.get('serial', 0)),
                    subject=ca_data.get('subject', ''),
                    issuer=ca_data.get('issuer', ''),
                    valid_from=ca_data.get('valid_from'),
                    valid_to=ca_data.get('valid_to'),
                    imported_from='opnsense'
                )
                
                # For intermediate CAs, try to find parent
                if not ca_data.get('is_root', False):
                    # Try to find parent CA by matching issuer
                    issuer = ca_data.get('issuer', '')
                    parent_ca = CA.query.filter_by(subject=issuer).first()
                    if parent_ca:
                        ca.caref = parent_ca.refid
                
                db.session.add(ca)
                db.session.flush()
                
                # Save certificate to file
                if ca_data.get('crt'):
                    import os
                    data_dir = os.path.join(
                        os.path.dirname(os.path.dirname(__file__)), "data"
                    )
                    ca_dir = os.path.join(data_dir, "ca")
                    os.makedirs(ca_dir, exist_ok=True)
                    
                    ca_file = os.path.join(ca_dir, f"{refid}.crt")
                    with open(ca_file, "wb") as f:
                        f.write(base64.b64decode(ca_data['crt']))
                    
                    # Save private key if present
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
                stats['errors'].append(f"CA {ca_data.get('refid', 'unknown')}: {str(e)}")
                print(f"Failed to import CA: {e}")
                import traceback
                traceback.print_exc()
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            stats['errors'].append(f"Database commit failed: {str(e)}")
        
        return stats
    
    def import_certificates(self, certs_data: List[Dict], 
                           skip_existing: bool = True) -> Dict:
        """
        Import certificates into UCM database
        
        Args:
            certs_data: List of certificate data dictionaries
            skip_existing: Skip if cert with same refid already exists
            
        Returns:
            Dict with import statistics
        """
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
                
                # Check if already exists
                if skip_existing:
                    existing = Certificate.query.filter_by(refid=refid).first()
                    if existing:
                        stats['skipped'] += 1
                        continue
                
                # Verify CA exists
                caref = cert_data.get('caref')
                if caref:
                    ca = CA.query.filter_by(refid=caref).first()
                    if not ca:
                        stats['failed'] += 1
                        stats['errors'].append(
                            f"Cert {refid}: CA {caref} not found"
                        )
                        continue
                
                # Parse certificate to extract SANs
                import json
                san_dns_list = []
                san_ip_list = []
                san_email_list = []
                san_uri_list = []
                
                if cert_data.get('crt'):
                    try:
                        from cryptography import x509
                        from cryptography.hazmat.backends import default_backend
                        cert_pem = base64.b64decode(cert_data['crt'])
                        x509_cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
                        
                        try:
                            ext = x509_cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
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
                            pass  # No SAN extension
                    except:
                        pass  # Ignore parsing errors
                
                # Create certificate record
                cert = Certificate(
                    refid=refid,
                    caref=caref,
                    descr=cert_data.get('descr', 'Imported from OPNsense'),
                    crt=cert_data.get('crt', ''),
                    prv=cert_data.get('prv'),  # May be None
                    cert_type=cert_data.get('type', 'server_cert'),
                    subject=cert_data.get('subject', ''),
                    issuer=cert_data.get('issuer', ''),
                    serial_number=cert_data.get('serial_number', ''),
                    valid_from=cert_data.get('valid_from'),
                    valid_to=cert_data.get('valid_to'),
                    # Store extracted SANs
                    san_dns=json.dumps(san_dns_list) if san_dns_list else None,
                    san_ip=json.dumps(san_ip_list) if san_ip_list else None,
                    san_email=json.dumps(san_email_list) if san_email_list else None,
                    san_uri=json.dumps(san_uri_list) if san_uri_list else None,
                    imported_from='opnsense',
                    created_by='import'
                )
                
                db.session.add(cert)
                db.session.flush()
                
                # Save certificate to file
                if cert_data.get('crt'):
                    import os
                    data_dir = os.path.join(
                        os.path.dirname(os.path.dirname(__file__)), "data"
                    )
                    certs_dir = os.path.join(data_dir, "certs")
                    os.makedirs(certs_dir, exist_ok=True)
                    
                    cert_file = os.path.join(certs_dir, f"{refid}.crt")
                    with open(cert_file, "wb") as f:
                        f.write(base64.b64decode(cert_data['crt']))
                    
                    # Save private key if present
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
                stats['errors'].append(
                    f"Cert {cert_data.get('refid', 'unknown')}: {str(e)}"
                )
                print(f"Failed to import certificate: {e}")
                import traceback
                traceback.print_exc()
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            stats['errors'].append(f"Database commit failed: {str(e)}")
        
        return stats
    
    def full_import(self, skip_existing: bool = True) -> Dict:
        """
        Perform full import of CAs and certificates
        
        Args:
            skip_existing: Skip items that already exist
            
        Returns:
            Dict with complete import statistics
        """
        import sys
        result = {
            'success': False,
            'connected': False,
            'config_retrieved': False,
            'cas': None,
            'certs': None,
            'errors': []
        }
        
        # Connect
        if not self.connect():
            result['errors'].append("Failed to connect to OPNsense")
            sys.stderr.write(f"ERROR full_import: Connection failed\n")
            sys.stderr.flush()
            return result
        
        result['connected'] = True
        sys.stderr.write(f"DEBUG full_import: Connected successfully\n")
        sys.stderr.flush()
        
        # Get config
        config_xml = self.get_config_xml()
        if not config_xml:
            result['errors'].append("Failed to retrieve config.xml")
            sys.stderr.write(f"ERROR full_import: Failed to get config.xml\n")
            sys.stderr.flush()
            return result
        
        result['config_retrieved'] = True
        sys.stderr.write(f"DEBUG full_import: Config retrieved ({len(config_xml)} bytes)\n")
        sys.stderr.flush()
        
        # Parse
        try:
            data = self.parse_trust_data(config_xml)
            sys.stderr.write(f"DEBUG full_import: Parsed {len(data['cas'])} CAs, {len(data['certs'])} certs\n")
            sys.stderr.flush()
        except Exception as e:
            result['errors'].append(f"Failed to parse config.xml: {str(e)}")
            sys.stderr.write(f"ERROR full_import: Parse failed: {str(e)}\n")
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            return result
        
        # Import CAs
        try:
            result['cas'] = self.import_cas(data['cas'], skip_existing)
            sys.stderr.write(f"DEBUG full_import: CA import result: {result['cas']}\n")
            sys.stderr.flush()
        except Exception as e:
            result['errors'].append(f"Failed to import CAs: {str(e)}")
            sys.stderr.write(f"ERROR full_import: CA import failed: {str(e)}\n")
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            result['cas'] = {'imported': 0, 'skipped': 0, 'errors': [str(e)]}
        
        # Import certificates
        try:
            result['certs'] = self.import_certificates(data['certs'], skip_existing)
            sys.stderr.write(f"DEBUG full_import: Cert import result: {result['certs']}\n")
            sys.stderr.flush()
        except Exception as e:
            result['errors'].append(f"Failed to import certificates: {str(e)}")
            sys.stderr.write(f"ERROR full_import: Cert import failed: {str(e)}\n")
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            result['certs'] = {'imported': 0, 'skipped': 0, 'errors': [str(e)]}
        
        # Success if at least one item imported OR if parsing/connection succeeded (even if all skipped)
        if (result['cas'] and result['certs']):
            total_imported = result['cas']['imported'] + result['certs']['imported']
            total_processed = total_imported + result['cas']['skipped'] + result['certs']['skipped']
            result['success'] = True  # Success if we processed items, even if all were skipped
            sys.stderr.write(f"DEBUG full_import: SUCCESS - Imported: {total_imported}, Skipped: {total_processed - total_imported}\n")
            sys.stderr.flush()
        
        return result


def get_import_config() -> Optional[Dict]:
    """Get OPNsense import configuration from system config"""
    config = SystemConfig.query.filter_by(key="opnsense_import_config").first()
    if not config:
        return None
    
    import json
    return json.loads(config.value)


def save_import_config(base_url: str, username: str = None, password: str = None,
                       api_key: str = None, api_secret: str = None,
                       verify_ssl: bool = False) -> None:
    """
    Save OPNsense import configuration
    
    Supports both authentication methods:
    - username/password for web scraping
    - api_key/api_secret for REST API (recommended)
    """
    import json
    
    config = SystemConfig.query.filter_by(key="opnsense_import_config").first()
    if not config:
        config = SystemConfig(key="opnsense_import_config")
        db.session.add(config)
    
    config_data = {
        "base_url": base_url,
        "verify_ssl": verify_ssl
    }
    
    # Store credentials based on auth method
    if api_key and api_secret:
        config_data["api_key"] = api_key
        config_data["api_secret"] = api_secret
        config_data["auth_method"] = "api"
    else:
        config_data["username"] = username
        config_data["password"] = password
        config_data["auth_method"] = "web"
    
    config.value = json.dumps(config_data)
    
    db.session.commit()
