"""
Chain Builder - Reconstruct certificate chains from parsed objects

Given a list of certificates, builds proper chain hierarchy:
- Identifies root CAs (self-signed)
- Links intermediates to their issuers
- Identifies leaf certificates
- Validates chain signatures
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import UnsupportedAlgorithm
from utils.cert_issuer import UnsupportedIssuerKey, verify_certificate_signature

from .parser import ParsedObject, ObjectType


def find_ca_by_ski(ski):
    """The stored CA with this SKI; at equal SKI the self-signed record, not a cross-certificate."""
    from sqlalchemy import case
    from models import CA
    return CA.query.filter_by(ski=ski).order_by(
        case((CA.subject == CA.issuer, 0), else_=1), CA.id).first()


@dataclass
class ChainInfo:
    """Information about a certificate chain"""
    root: Optional[ParsedObject] = None
    intermediates: List[ParsedObject] = None
    leaf: Optional[ParsedObject] = None
    is_complete: bool = False
    is_valid: bool = False
    verifiable: bool = True  # False when a signature uses an algorithm UCM cannot check
    errors: List[str] = None
    trust_source: Optional[str] = None  # 'self_contained', 'managed_ca', 'trust_store', None
    trust_anchor: Optional[str] = None  # Name of the trust anchor (CA name)
    
    def __post_init__(self):
        if self.intermediates is None:
            self.intermediates = []
        if self.errors is None:
            self.errors = []
    
    def to_dict(self) -> Dict:
        return {
            "root": self.root.to_dict() if self.root else None,
            "intermediates": [i.to_dict() for i in self.intermediates],
            "leaf": self.leaf.to_dict() if self.leaf else None,
            "is_complete": self.is_complete,
            "is_valid": self.is_valid,
            "verifiable": self.verifiable,
            "errors": self.errors,
            "chain_length": len(self.get_ordered_chain()),
            "trust_source": self.trust_source,
            "trust_anchor": self.trust_anchor,
        }
    
    def get_ordered_chain(self) -> List[ParsedObject]:
        """Return chain in order: leaf -> intermediates -> root"""
        chain = []
        if self.leaf:
            chain.append(self.leaf)
        chain.extend(self.intermediates)
        if self.root:
            chain.append(self.root)
        return chain


class ChainBuilder:
    """
    Builds certificate chains from unordered certificate lists.
    """
    
    def build_chains(self, objects: List[ParsedObject]) -> List[ChainInfo]:
        """
        Build all possible chains from a list of parsed objects.
        
        Args:
            objects: List of ParsedObject (certificates)
            
        Returns:
            List of ChainInfo representing detected chains
        """
        # Filter only certificates
        certs = [o for o in objects if o.type == ObjectType.CERTIFICATE]
        
        if not certs:
            return []
        
        # Build subject -> cert mapping
        subject_map: Dict[str, List[ParsedObject]] = {}
        ski_map: Dict[str, ParsedObject] = {}  # SKI → cert for AKI→SKI matching
        for cert in certs:
            if cert.subject not in subject_map:
                subject_map[cert.subject] = []
            subject_map[cert.subject].append(cert)
            # At equal SKI the self-signed certificate stands for the key, not its cross-certificates
            if cert.ski and not (cert.ski in ski_map and ski_map[cert.ski].is_self_signed):
                ski_map[cert.ski] = cert
        
        # Find root CAs (self-signed)
        roots = [c for c in certs if c.is_self_signed and c.is_ca]
        
        # Find leaf certificates (not CA)
        leaves = [c for c in certs if not c.is_ca]
        
        # Find intermediates (CA but not self-signed)
        intermediates = [c for c in certs if c.is_ca and not c.is_self_signed]
        
        chains: List[ChainInfo] = []
        
        # Build chain for each leaf
        for leaf in leaves:
            chain = self._build_chain_for_leaf(leaf, subject_map, ski_map, certs)
            chains.append(chain)
        
        # If no leaves, maybe we're importing just CAs
        if not leaves and (roots or intermediates):
            # Return CA-only chain info
            chain = ChainInfo()
            if len(roots) == 1:
                chain.root = roots[0]
                roots[0].chain_position = "root"
                roots[0].chain_depth = 0
            chain.intermediates = intermediates
            for i, inter in enumerate(intermediates):
                inter.chain_position = "intermediate"
                inter.chain_depth = i + 1
            chain.is_complete = bool(roots)
            chains.append(chain)
        
        # Validate each chain
        for chain in chains:
            self._validate_chain(chain)
        
        return chains
    
    def _build_chain_for_leaf(
        self, 
        leaf: ParsedObject, 
        subject_map: Dict[str, List[ParsedObject]],
        ski_map: Dict[str, ParsedObject],
        all_certs: List[ParsedObject]
    ) -> ChainInfo:
        """Build chain starting from a leaf certificate"""
        chain = ChainInfo()
        chain.leaf = leaf
        leaf.chain_position = "leaf"
        leaf.chain_depth = 0
        
        # Walk up the chain
        current = leaf
        depth = 1
        visited = {leaf.serial_number}
        
        while True:
            # Find issuer: AKI→SKI first, then issuer DN fallback
            issuer_cert = None
            if current.aki and current.aki in ski_map:
                candidate = ski_map[current.aki]
                if candidate.serial_number not in visited and candidate.serial_number != current.serial_number:
                    issuer_cert = candidate
            
            if not issuer_cert:
                issuer_certs = subject_map.get(current.issuer, [])
                issuer_certs = [
                    c for c in issuer_certs 
                    if c.serial_number not in visited and c.serial_number != current.serial_number
                ]
                if not issuer_certs:
                    break
                issuer_cert = next((c for c in issuer_certs if c.is_ca and c.is_self_signed),
                                   next((c for c in issuer_certs if c.is_ca), issuer_certs[0]))
            
            visited.add(issuer_cert.serial_number)
            
            if issuer_cert.is_self_signed:
                # Found root
                chain.root = issuer_cert
                issuer_cert.chain_position = "root"
                issuer_cert.chain_depth = depth
                chain.is_complete = True
                break
            else:
                # Intermediate
                chain.intermediates.append(issuer_cert)
                issuer_cert.chain_position = "intermediate"
                issuer_cert.chain_depth = depth
                current = issuer_cert
                depth += 1
            
            # Safety limit
            if depth > 10:
                chain.errors.append("Chain depth exceeds limit (possible loop)")
                break
        
        return chain
    
    def _validate_chain(self, chain: ChainInfo) -> None:
        """Validate signatures in the chain"""
        ordered = chain.get_ordered_chain()
        
        if len(ordered) < 2:
            chain.is_valid = True  # Single cert, no validation needed
            return
        
        chain.is_valid = True
        
        for i in range(len(ordered) - 1):
            child = ordered[i]
            parent = ordered[i + 1]
            
            try:
                # Load certificates
                child_cert = x509.load_pem_x509_certificate(
                    child.raw_pem.encode(), default_backend()
                )
                parent_cert = x509.load_pem_x509_certificate(
                    parent.raw_pem.encode(), default_backend()
                )
                
                # Verify signature
                self._verify_signature(child_cert, parent_cert.public_key())

            except (UnsupportedIssuerKey, UnsupportedAlgorithm) as e:
                chain.is_valid = False
                chain.verifiable = False
                chain.errors.append(
                    f"Signature not verifiable: {child.subject} signed by {parent.subject}: {e}"
                )
            except Exception as e:
                chain.is_valid = False
                chain.errors.append(
                    f"Signature verification failed: {child.subject} signed by {parent.subject}: {str(e)}"
                )
    
    def _verify_signature(self, cert: x509.Certificate, issuer_public_key) -> bool:
        """Verify certificate signature (raises on failure)"""
        verify_certificate_signature(cert, issuer_public_key)
        return True
    
    def find_issuer_in_db(self, cert: ParsedObject) -> Optional[str]:
        """
        Try to find the issuing CA in the database.
        Uses AKI→SKI matching first (cryptographically reliable),
        then falls back to issuer DN matching.
        
        Returns CA refid if found, None otherwise.
        """
        from models import CA
        
        # AKI→SKI matching (reliable)
        if cert.aki:
            ca = find_ca_by_ski(cert.aki)
            if ca:
                return ca.refid
        
        # Fallback: issuer DN matching
        ca = CA.query.filter(CA.subject == cert.issuer).first()
        if ca:
            return ca.refid
        
        return None
