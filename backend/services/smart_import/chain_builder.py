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
from cryptography.hazmat.primitives.asymmetric import padding, ec

from .parser import ParsedObject, ObjectType


@dataclass
class ChainInfo:
    """Information about a certificate chain"""
    root: Optional[ParsedObject] = None
    intermediates: List[ParsedObject] = None
    leaf: Optional[ParsedObject] = None
    is_complete: bool = False
    is_valid: bool = False
    errors: List[str] = None
    
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
            "errors": self.errors,
            "chain_length": len(self.get_ordered_chain())
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
            if cert.ski:
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
                issuer_cert = next((c for c in issuer_certs if c.is_ca), issuer_certs[0])
            
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
                
            except Exception as e:
                chain.is_valid = False
                chain.errors.append(
                    f"Signature verification failed: {child.subject} signed by {parent.subject}: {str(e)}"
                )
    
    def _verify_signature(self, cert: x509.Certificate, issuer_public_key) -> bool:
        """Verify certificate signature"""
        from cryptography.hazmat.primitives.asymmetric import rsa, ec, ed25519, ed448
        
        try:
            if isinstance(issuer_public_key, rsa.RSAPublicKey):
                issuer_public_key.verify(
                    cert.signature,
                    cert.tbs_certificate_bytes,
                    padding.PKCS1v15(),
                    cert.signature_hash_algorithm
                )
            elif isinstance(issuer_public_key, ec.EllipticCurvePublicKey):
                issuer_public_key.verify(
                    cert.signature,
                    cert.tbs_certificate_bytes,
                    ec.ECDSA(cert.signature_hash_algorithm)
                )
            elif isinstance(issuer_public_key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
                issuer_public_key.verify(cert.signature, cert.tbs_certificate_bytes)
            else:
                raise ValueError(f"Unsupported key type: {type(issuer_public_key)}")
            return True
        except Exception:
            raise
    
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
            ca = CA.query.filter_by(ski=cert.aki).first()
            if ca:
                return ca.refid
        
        # Fallback: issuer DN matching
        ca = CA.query.filter(CA.subject == cert.issuer).first()
        if ca:
            return ca.refid
        
        return None
