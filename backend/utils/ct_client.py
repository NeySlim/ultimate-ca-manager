"""
Certificate Transparency — SCT Embedding (RFC 6962)

Submits pre-certificates to CT logs and embeds Signed Certificate
Timestamps (SCTs) in issued certificates.
"""
import base64
import hashlib
import json
import logging
import struct
import time
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Well-known CT log URLs
DEFAULT_CT_LOGS = [
    # Google Argon logs
    "https://ct.googleapis.com/logs/argon2025h1/",
    "https://ct.googleapis.com/logs/argon2025h2/",
]

# SCT Extension OID: 1.3.6.1.4.1.11129.2.4.2
SCT_LIST_OID = "1.3.6.1.4.1.11129.2.4.2"


def submit_to_ct_log(log_url: str, cert_chain_pem: List[str], timeout: int = 10) -> Optional[Dict[str, Any]]:
    """Submit a certificate chain to a CT log and get an SCT back.
    
    Args:
        log_url: CT log submission URL
        cert_chain_pem: List of PEM certificates (leaf first, then intermediates)
        timeout: Request timeout in seconds
        
    Returns:
        SCT dict with {sct_version, id, timestamp, extensions, signature} or None
    """
    import urllib.request
    import ssl
    
    try:
        # Convert PEM chain to base64 DER entries
        chain_b64 = []
        for pem in cert_chain_pem:
            # Strip PEM headers
            lines = pem.strip().split('\n')
            b64_data = ''.join(
                line for line in lines
                if not line.startswith('-----')
            )
            chain_b64.append(b64_data)
        
        # Build request body
        payload = json.dumps({
            "chain": chain_b64
        }).encode('utf-8')
        
        submit_url = log_url.rstrip('/') + '/ct/v1/add-chain'

        # CT log URLs are admin-configurable; block cloud-metadata/loopback
        # targets so a misconfigured URL can't be used to probe internals.
        # (LAN/public remain allowed — CT logs are public infra.)
        from utils.ssrf_protection import validate_url_not_cloud_metadata
        try:
            validate_url_not_cloud_metadata(submit_url)
        except ValueError as e:
            logger.warning(f"CT log submission to {log_url} rejected: {e}")
            return None

        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            submit_url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
        result = json.loads(resp.read().decode('utf-8'))
        
        return result
        
    except Exception as e:
        logger.warning(f"CT log submission to {log_url} failed: {e}")
        return None


def collect_scts(cert_chain_pem: List[str], ct_log_urls: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Submit certificate to multiple CT logs and collect SCTs.
    
    Args:
        cert_chain_pem: PEM certificate chain (leaf first)
        ct_log_urls: List of CT log URLs (defaults to well-known logs)
        
    Returns:
        List of SCT dicts
    """
    if ct_log_urls is None:
        ct_log_urls = DEFAULT_CT_LOGS
    
    scts = []
    for log_url in ct_log_urls:
        sct = submit_to_ct_log(log_url, cert_chain_pem)
        if sct:
            scts.append(sct)
            logger.info(f"Got SCT from {log_url}")
    
    return scts


def encode_sct_list(scts: List[Dict[str, Any]]) -> bytes:
    """Encode a list of SCTs into the SCT list format per RFC 6962 §3.3.
    
    The SCT list is a serialized TransItemList containing
    SignedCertificateTimestamp structures.
    
    Args:
        scts: List of SCT dicts from CT log responses
        
    Returns:
        DER-encoded SCT list for embedding as X.509 extension value
    """
    encoded_scts = []
    
    for sct in scts:
        try:
            # Parse SCT components
            version = sct.get('sct_version', 0)
            log_id = base64.b64decode(sct.get('id', ''))
            timestamp = sct.get('timestamp', int(time.time() * 1000))
            extensions = base64.b64decode(sct.get('extensions', ''))
            signature = base64.b64decode(sct.get('signature', ''))
            
            # Encode single SCT
            sct_data = struct.pack('!B', version)  # Version (1 byte)
            sct_data += log_id  # LogID (32 bytes)
            sct_data += struct.pack('!Q', timestamp)  # Timestamp (8 bytes)
            sct_data += struct.pack('!H', len(extensions))  # Extensions length
            sct_data += extensions  # Extensions
            sct_data += signature  # DigitallySigned
            
            # Wrap with length prefix (2 bytes)
            encoded_scts.append(struct.pack('!H', len(sct_data)) + sct_data)
        except Exception as e:
            logger.warning(f"Failed to encode SCT: {e}")
            continue
    
    if not encoded_scts:
        return b''
    
    # Concatenate all encoded SCTs
    sct_list_data = b''.join(encoded_scts)
    
    # Wrap with total length (2 bytes)
    return struct.pack('!H', len(sct_list_data)) + sct_list_data
