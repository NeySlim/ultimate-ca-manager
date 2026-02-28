"""
Discovery Service
Scans network targets for TLS certificates and imports them into UCM
"""
import socket
import ssl
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import ExtensionOID
import ipaddress
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from models import db, DiscoveredCertificate, Certificate
from services.certificate_parser import CertificateParser
from services.cert_service import CertificateService

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Service for discovering certificates on the network"""
    
    def __init__(self, max_workers: int = 10, timeout: int = 10):
        """
        Initialize Discovery Service
        
        Args:
            max_workers: Maximum number of concurrent connections
            timeout: Connection timeout in seconds
        """
        self.max_workers = max_workers
        self.timeout = timeout
        self.certificate_service = CertificateService()
    
    def get_certificate_from_tls(self, host: str, port: int = 443) -> Optional[Dict]:
        """
        Retrieve certificate from a TLS endpoint
        
        Args:
            host: Target hostname or IP
            port: Target port (default: 443)
            
        Returns:
            Dictionary with certificate information or None if failed
        """
        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            with socket.create_connection((host, port), timeout=self.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=host) as ssock:
                    cert_der = ssock.getpeercert(binary_form=True)
                    if cert_der:
                        cert = x509.load_der_x509_certificate(cert_der, default_backend())
                        return self._cert_to_dict(cert, host, port)
        except Exception as e:
            logger.debug(f"Failed to get certificate from {host}:{port} - {e}")
        return None
    
    def _cert_to_dict(self, cert: x509.Certificate, host: str, port: int) -> Dict:
        """
        Convert x509 certificate to dictionary
        
        Args:
            cert: x509.Certificate object
            host: Target hostname
            port: Target port
            
        Returns:
            Dictionary with certificate information
        """
        return {
            'target': f'{host}:{port}',
            'certificate': cert.public_bytes(encoding=serialization.Encoding.PEM).decode(),
            'issuer': str(cert.issuer),
            'subject': str(cert.subject),
            'serial': hex(cert.serial_number),
            'not_before': cert.not_valid_before,
            'not_after': cert.not_valid_after,
            'fingerprint': self._get_fingerprint(cert),
        }
    
    def _get_fingerprint(self, cert: x509.Certificate) -> str:
        """
        Calculate SHA-256 fingerprint of certificate
        
        Args:
            cert: x509.Certificate object
            
        Returns:
            SHA-256 fingerprint as hex string
        """
        fingerprint = hashlib.sha256(
            cert.public_bytes(encoding=serialization.Encoding.DER)
        ).hexdigest()
        return fingerprint.upper()
    
    def scan_target(self, target: str, port: int = 443) -> Optional[Dict]:
        """
        Scan a single target
        
        Args:
            target: Target hostname or IP
            port: Target port (default: 443)
            
        Returns:
            Dictionary with certificate information or None
        """
        host = target
        if ':' in target and not target.startswith('['):
            host, port = target.split(':')
            port = int(port)
        
        return self.get_certificate_from_tls(host, port)
    
    def scan_targets(self, targets: List[str], ports: List[int] = None) -> List[Dict]:
        """
        Scan multiple targets
        
        Args:
            targets: List of target hostnames or IPs
            ports: List of ports to scan (default: [443, 8443])
            
        Returns:
            List of discovered certificates
        """
        if ports is None:
            ports = [443, 8443]
        
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for target in targets:
                for port in ports:
                    futures.append(executor.submit(self.scan_target, target, port))
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
        
        return results
    
    def scan_subnet(self, subnet_cidr: str, ports: List[int] = None) -> List[Dict]:
        """
        Scan a subnet for certificates
        
        Args:
            subnet_cidr: Subnet in CIDR notation (e.g., '192.168.1.0/24')
            ports: List of ports to scan (default: [443, 8443])
            
        Returns:
            List of discovered certificates
        """
        if ports is None:
            ports = [443, 8443]
        
        network = ipaddress.ip_network(subnet_cidr, strict=False)
        targets = [str(ip) for ip in network.hosts()]
        
        return self.scan_targets(targets, ports)
    
    def import_to_ucm(self, discovered_cert: Dict) -> DiscoveredCertificate:
        """
        Import a discovered certificate into UCM
        
        Args:
            discovered_cert: Dictionary with certificate information
            
        Returns:
            DiscoveredCertificate model instance
        """
        # Check if certificate already exists in UCM
        fingerprint = discovered_cert['fingerprint']
        existing = Certificate.query.filter_by(fingerprint=fingerprint).first()
        
        status = 'known' if existing else 'unknown'
        ucm_certificate_id = existing.id if existing else None
        
        # Create discovered certificate record
        disc_cert = DiscoveredCertificate(
            target=discovered_cert['target'],
            certificate=discovered_cert['certificate'],
            issuer=discovered_cert['issuer'],
            subject=discovered_cert['subject'],
            serial=discovered_cert['serial'],
            not_before=discovered_cert['not_before'],
            not_after=discovered_cert['not_after'],
            fingerprint=fingerprint,
            status=status,
            ucm_certificate_id=ucm_certificate_id
        )
        
        db.session.add(disc_cert)
        db.session.commit()
        
        return disc_cert
    
    def import_multiple(self, certificates: List[Dict]) -> Tuple[int, int]:
        """
        Import multiple discovered certificates
        
        Args:
            certificates: List of certificate dictionaries
            
        Returns:
            Tuple of (total_imported, already_known)
        """
        imported = 0
        known = 0
        
        for cert in certificates:
            fingerprint = cert['fingerprint']
            existing = Certificate.query.filter_by(fingerprint=fingerprint).first()
            
            if existing:
                known += 1
            else:
                self.import_to_ucm(cert)
                imported += 1
        
        return imported, known
    
    def get_discovery_history(self, limit: int = 100) -> List[Dict]:
        """
        Get discovery history
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of discovered certificates
        """
        history = DiscoveredCertificate.query.order_by(
            DiscoveredCertificate.last_seen.desc()
        ).limit(limit).all()
        
        return [h.to_dict() for h in history]
    
    def get_unknown_certificates(self) -> List[Dict]:
        """
        Get certificates that are not in UCM
        
        Returns:
            List of unknown certificates
        """
        unknown = DiscoveredCertificate.query.filter_by(
            status='unknown'
        ).order_by(
            DiscoveredCertificate.last_seen.desc()
        ).all()
        
        return [c.to_dict() for c in unknown]
    
    def get_expired_certificates(self) -> List[Dict]:
        """
        Get expired discovered certificates
        
        Returns:
            List of expired certificates
        """
        expired = DiscoveredCertificate.query.filter(
            DiscoveredCertificate.not_after < datetime.utcnow()
        ).order_by(
            DiscoveredCertificate.not_after.asc()
        ).all()
        
        return [c.to_dict() for c in expired]
    
    def run_scheduled_scan(self, targets: List[str] = None, ports: List[int] = None):
        """
        Run a scheduled scan (can be registered in scheduler)
        
        Args:
            targets: List of targets to scan (if None, uses configured targets)
            ports: List of ports to scan
            
        Returns:
            Dictionary with scan results
        """
        if not targets:
            # In a real implementation, you would load targets from config
            targets = ['example.com', 'google.com']
        
        results = self.scan_targets(targets, ports)
        
        # Import results
        imported, known = self.import_multiple(results)
        
        logger.info(f"Discovery scan completed: {len(results)} found, {imported} imported, {known} already known")
        
        return {
            'total_scanned': len(targets),
            'certificates_found': len(results),
            'imported': imported,
            'already_known': known
        }
