"""
Smart Importer - Execute the actual import of parsed objects

Handles:
- Certificate import (with chain building)
- CA import (respecting hierarchy)
- Key association
- CSR import
- Audit logging
"""

import base64
import secrets
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from models import db, Certificate, CA, AuditLog
from .parser import ParsedObject, ObjectType, SmartParser
from .chain_builder import ChainBuilder, ChainInfo
from .matcher import KeyMatcher
from .validator import ImportValidator, ValidationResult


@dataclass
class ImportResult:
    """Result of an import operation"""
    success: bool = True
    certificates_imported: int = 0
    cas_imported: int = 0
    keys_matched: int = 0
    csrs_imported: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    imported_ids: Dict[str, List[int]] = field(default_factory=lambda: {
        "certificates": [],
        "cas": [],
        "csrs": []
    })
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "certificates_imported": self.certificates_imported,
            "cas_imported": self.cas_imported,
            "keys_matched": self.keys_matched,
            "csrs_imported": self.csrs_imported,
            "errors": self.errors,
            "warnings": self.warnings,
            "imported_ids": self.imported_ids
        }


@dataclass
class AnalysisResult:
    """Result of content analysis (before import)"""
    objects: List[Dict] = field(default_factory=list)
    chains: List[Dict] = field(default_factory=list)
    matching: Dict = field(default_factory=dict)
    validation: Dict = field(default_factory=dict)
    summary: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "objects": self.objects,
            "chains": self.chains,
            "matching": self.matching,
            "validation": self.validation,
            "summary": self.summary
        }


class SmartImporter:
    """
    Main class for smart import operations.
    
    Usage:
        importer = SmartImporter()
        
        # Step 1: Analyze content
        analysis = importer.analyze(content, password)
        
        # Step 2: Execute import (after user confirmation)
        result = importer.execute(content, password, options)
    """
    
    def __init__(self):
        self.parser = SmartParser()
        self.chain_builder = ChainBuilder()
        self.matcher = KeyMatcher()
        self.validator = ImportValidator()
    
    def analyze(self, content: str | bytes, password: Optional[str] = None) -> AnalysisResult:
        """
        Analyze content without importing.
        
        Args:
            content: PEM/DER/PKCS12 content
            password: Optional password for encrypted content
            
        Returns:
            AnalysisResult with detected objects and validation info
        """
        result = AnalysisResult()
        
        # Parse content
        objects = self.parser.parse(content, password)
        result.objects = [o.to_dict() for o in objects]
        
        # Build chains
        chains = self.chain_builder.build_chains(objects)
        result.chains = [c.to_dict() for c in chains]
        
        # Match keys
        matching = self.matcher.match_all(objects)
        result.matching = matching
        
        # Validate
        validation = self.validator.validate_all(objects, chains)
        result.validation = validation.to_dict()
        
        # Summary
        certs = [o for o in objects if o.type == ObjectType.CERTIFICATE]
        cas = [o for o in objects if o.type == ObjectType.CERTIFICATE and o.is_ca]
        keys = [o for o in objects if o.type == ObjectType.PRIVATE_KEY]
        csrs = [o for o in objects if o.type == ObjectType.CSR]
        
        result.summary = {
            "total_objects": len(objects),
            "certificates": len(certs) - len(cas),  # Leaf certs only
            "cas": len(cas),
            "private_keys": len(keys),
            "csrs": len(csrs),
            "matched_key_pairs": len(matching.get("matched_pairs", [])),
            "orphan_keys": len(matching.get("orphan_keys", [])),
            "chains_complete": sum(1 for c in chains if c.is_complete),
            "chains_incomplete": sum(1 for c in chains if not c.is_complete),
            "is_valid": validation.is_valid,
            "error_count": len(validation.errors),
            "warning_count": len(validation.warnings)
        }
        
        return result
    
    def execute(
        self,
        content: str | bytes,
        password: Optional[str] = None,
        options: Optional[Dict] = None,
        username: str = "system"
    ) -> ImportResult:
        """
        Execute the import.
        
        Args:
            content: PEM/DER/PKCS12 content
            password: Optional password
            options: Import options:
                - import_cas: bool (default True)
                - import_certs: bool (default True)
                - import_csrs: bool (default True)
                - skip_duplicates: bool (default True)
                - description_prefix: str (default "Imported: ")
            username: User performing import
            
        Returns:
            ImportResult with import details
        """
        options = options or {}
        import_cas = options.get("import_cas", True)
        import_certs = options.get("import_certs", True)
        import_csrs = options.get("import_csrs", True)
        skip_duplicates = options.get("skip_duplicates", True)
        desc_prefix = options.get("description_prefix", "Imported: ")
        
        result = ImportResult()
        
        try:
            # Parse
            objects = self.parser.parse(content, password)
            
            # Build chains
            chains = self.chain_builder.build_chains(objects)
            
            # Match keys
            matching = self.matcher.match_all(objects)
            
            # Import CAs first (respecting hierarchy)
            if import_cas:
                self._import_cas(objects, chains, matching, result, desc_prefix, username, skip_duplicates)
            
            # Import certificates
            if import_certs:
                self._import_certificates(objects, chains, matching, result, desc_prefix, username, skip_duplicates)
            
            # Import CSRs
            if import_csrs:
                self._import_csrs(objects, matching, result, desc_prefix, username)
            
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            result.success = False
            result.errors.append(f"Import failed: {str(e)}")
        
        return result
    
    def _import_cas(
        self,
        objects: List[ParsedObject],
        chains: List[ChainInfo],
        matching: Dict,
        result: ImportResult,
        desc_prefix: str,
        username: str,
        skip_duplicates: bool
    ):
        """Import CA certificates"""
        
        # Get all CAs from objects
        ca_objects = [o for o in objects if o.type == ObjectType.CERTIFICATE and o.is_ca]
        
        # Sort by chain depth (roots first)
        ca_objects.sort(key=lambda o: o.chain_depth, reverse=True)
        
        # Map old subject to new refid for parent linking
        subject_to_refid: Dict[str, str] = {}
        ski_to_refid: Dict[str, str] = {}
        
        for ca_obj in ca_objects:
            # Check duplicate by SKI first, then serial_number
            if skip_duplicates:
                existing = None
                if ca_obj.ski:
                    existing = CA.query.filter_by(ski=ca_obj.ski).first()
                if not existing and ca_obj.serial_number:
                    existing = CA.query.filter_by(serial_number=ca_obj.serial_number).first()
                if existing:
                    result.warnings.append(f"Skipped duplicate CA: {self._get_cn(ca_obj.subject)}")
                    subject_to_refid[ca_obj.subject] = existing.refid
                    if existing.ski:
                        ski_to_refid[existing.ski] = existing.refid
                    continue
            
            # Find parent CA: AKI→SKI first, then issuer DN fallback
            caref = None
            if not ca_obj.is_self_signed:
                if ca_obj.aki:
                    caref = ski_to_refid.get(ca_obj.aki)
                    if not caref:
                        parent = CA.query.filter_by(ski=ca_obj.aki).first()
                        if parent:
                            caref = parent.refid
                if not caref:
                    caref = subject_to_refid.get(ca_obj.issuer)
                if not caref:
                    parent = CA.query.filter(CA.subject == ca_obj.issuer).first()
                    if parent:
                        caref = parent.refid
            
            # Find matching private key
            prv = None
            for key_idx, cert_idx in matching.get("matched_pairs", []):
                if objects[cert_idx] == ca_obj:
                    key_obj = objects[key_idx]
                    prv = base64.b64encode(key_obj.raw_pem.encode()).decode()
                    result.keys_matched += 1
                    break
            
            # Create CA
            refid = secrets.token_hex(8)
            ca = CA(
                refid=refid,
                descr=self._get_cn(ca_obj.subject),
                caref=caref,
                crt=base64.b64encode(ca_obj.raw_pem.encode()).decode(),
                prv=prv,
                subject=ca_obj.subject,
                issuer=ca_obj.issuer,
                serial_number=ca_obj.serial_number,
                ski=ca_obj.ski,
                valid_from=datetime.fromisoformat(ca_obj.not_before.replace('Z', '+00:00')) if ca_obj.not_before else None,
                valid_to=datetime.fromisoformat(ca_obj.not_after.replace('Z', '+00:00')) if ca_obj.not_after else None,
                imported_from="smart_import",
                created_by=username
            )
            
            db.session.add(ca)
            db.session.flush()
            
            subject_to_refid[ca_obj.subject] = refid
            if ca_obj.ski:
                ski_to_refid[ca_obj.ski] = refid
            result.cas_imported += 1
            result.imported_ids["cas"].append(ca.id)
            
            # Audit log
            self._log_audit("import_ca", ca.id, ca.descr, username)
    
    def _import_certificates(
        self,
        objects: List[ParsedObject],
        chains: List[ChainInfo],
        matching: Dict,
        result: ImportResult,
        desc_prefix: str,
        username: str,
        skip_duplicates: bool
    ):
        """Import leaf certificates"""
        
        # Get leaf certificates (not CAs)
        cert_objects = [o for o in objects if o.type == ObjectType.CERTIFICATE and not o.is_ca]
        
        for cert_obj in cert_objects:
            # Check duplicate
            if skip_duplicates:
                existing = Certificate.query.filter_by(serial_number=cert_obj.serial_number).first()
                if existing:
                    result.warnings.append(f"Skipped duplicate certificate: {self._get_cn(cert_obj.subject)}")
                    continue
            
            # Find issuing CA: AKI→SKI first, then issuer DN fallback
            caref = None
            if cert_obj.aki:
                ca = CA.query.filter_by(ski=cert_obj.aki).first()
                if ca:
                    caref = ca.refid
            if not caref:
                ca = CA.query.filter(CA.subject == cert_obj.issuer).first()
                if ca:
                    caref = ca.refid
            
            # Find matching private key
            prv = None
            for key_idx, cert_idx in matching.get("matched_pairs", []):
                if objects[cert_idx] == cert_obj:
                    key_obj = objects[key_idx]
                    prv = base64.b64encode(key_obj.raw_pem.encode()).decode()
                    result.keys_matched += 1
                    break
            
            # Extract CN for subject_cn
            cn = self._get_cn(cert_obj.subject)
            if not cn or cn == "Unknown":
                cn = cert_obj.san_dns[0] if cert_obj.san_dns else None
            
            # Create certificate
            import json
            cert = Certificate(
                refid=secrets.token_urlsafe(16),
                descr=cn or 'Certificate',
                caref=caref,
                crt=base64.b64encode(cert_obj.raw_pem.encode()).decode(),
                prv=prv,
                cert_type="server_cert",
                subject=cert_obj.subject,
                subject_cn=cn,
                issuer=cert_obj.issuer,
                serial_number=cert_obj.serial_number,
                aki=cert_obj.aki,
                ski=cert_obj.ski,
                valid_from=datetime.fromisoformat(cert_obj.not_before.replace('Z', '+00:00')) if cert_obj.not_before else None,
                valid_to=datetime.fromisoformat(cert_obj.not_after.replace('Z', '+00:00')) if cert_obj.not_after else None,
                san_dns=json.dumps(cert_obj.san_dns) if cert_obj.san_dns else None,
                san_ip=json.dumps(cert_obj.san_ip) if cert_obj.san_ip else None,
                source="import",
                imported_from="smart_import",
                created_by=username
            )
            
            db.session.add(cert)
            db.session.flush()
            
            result.certificates_imported += 1
            result.imported_ids["certificates"].append(cert.id)
            
            # Audit log
            self._log_audit("import_certificate", cert.id, cert.descr, username)
    
    def _import_csrs(
        self,
        objects: List[ParsedObject],
        matching: Dict,
        result: ImportResult,
        desc_prefix: str,
        username: str
    ):
        """Import CSRs"""
        
        csr_objects = [o for o in objects if o.type == ObjectType.CSR]
        
        for csr_obj in csr_objects:
            cn = self._get_cn(csr_obj.subject)
            if not cn or cn == "Unknown":
                cn = csr_obj.san_dns[0] if csr_obj.san_dns else "CSR"
            
            # Find matching private key
            prv = None
            for csr_idx, key_idx in matching.get("csr_key_pairs", []):
                if objects[csr_idx] == csr_obj:
                    key_obj = objects[key_idx]
                    prv = base64.b64encode(key_obj.raw_pem.encode()).decode()
                    result.keys_matched += 1
                    break
            
            # Create certificate entry for CSR (without crt)
            import json
            cert = Certificate(
                refid=secrets.token_urlsafe(16),
                descr=cn,
                csr=base64.b64encode(csr_obj.raw_pem.encode()).decode(),
                prv=prv,
                cert_type="server_cert",
                subject=csr_obj.subject,
                subject_cn=cn,
                san_dns=json.dumps(csr_obj.san_dns) if csr_obj.san_dns else None,
                san_ip=json.dumps(csr_obj.san_ip) if csr_obj.san_ip else None,
                source="import",
                imported_from="smart_import",
                created_by=username
            )
            
            db.session.add(cert)
            db.session.flush()
            
            result.csrs_imported += 1
            result.imported_ids["csrs"].append(cert.id)
            
            # Audit log
            self._log_audit("import_csr", cert.id, cert.descr, username)
    
    def _get_cn(self, subject: str) -> str:
        """Extract CN from subject"""
        if not subject:
            return "Unknown"
        for part in subject.split(','):
            if part.strip().upper().startswith('CN='):
                return part.strip()[3:]
        return "Unknown"
    
    def _log_audit(self, action: str, resource_id: int, resource_name: str, username: str):
        """Create audit log entry"""
        try:
            log = AuditLog(
                timestamp=datetime.utcnow(),
                username=username,
                action=action,
                resource_type="certificate" if "csr" in action or "certificate" in action else "ca",
                resource_id=str(resource_id),
                resource_name=resource_name,
                success=True
            )
            db.session.add(log)
        except Exception:
            pass  # Don't fail import if audit fails
