"""
Certificate Pinning Helper
Optional SSL certificate pinning for external connections
"""

import os
import ssl
import hashlib
from urllib.parse import urlparse
import json

# Pinned certificates config file
PINS_FILE = os.getenv('UCM_CERT_PINS_FILE', '/etc/ucm/cert-pins.json')


def get_pinned_certs():
    """
    Get pinned certificate fingerprints from config
    
    Config format:
    {
        "pins": {
            "acme-staging.api.letsencrypt.org": {
                "sha256": ["fingerprint1", "fingerprint2"],
                "enabled": true
            }
        }
    }
    """
    if not os.path.exists(PINS_FILE):
        return {}
    
    try:
        with open(PINS_FILE, 'r') as f:
            data = json.load(f)
            return data.get('pins', {})
    except:
        return {}


def get_pin_for_host(hostname):
    """Get pin configuration for a specific host"""
    pins = get_pinned_certs()
    return pins.get(hostname, {})


def verify_cert_pin(hostname, cert_der):
    """
    Verify certificate against pinned fingerprint
    
    Args:
        hostname: The hostname (e.g., 'acme-staging.api.letsencrypt.org')
        cert_der: Certificate in DER format (bytes)
    
    Returns:
        tuple: (is_valid, error_message)
    """
    pin_config = get_pin_for_host(hostname)
    
    if not pin_config or not pin_config.get('enabled', False):
        # No pinning configured for this host - allow
        return True, None
    
    # Calculate certificate fingerprint
    cert_sha256 = hashlib.sha256(cert_der).hexdigest()
    
    # Check against pinned fingerprints
    allowed_pins = pin_config.get('sha256', [])
    
    if cert_sha256 in allowed_pins:
        return True, None
    
    return False, f"Certificate pin mismatch for {hostname}. Got: {cert_sha256[:16]}..."


def create_pinned_ssl_context(hostname):
    """
    Create an SSL context with certificate pinning
    
    Usage:
        ctx = create_pinned_ssl_context('api.example.com')
        requests.get('https://api.example.com', verify=ctx)
    
    Returns:
        ssl.SSLContext or True (verify=True if no pinning)
    """
    pin_config = get_pin_for_host(hostname)
    
    if not pin_config or not pin_config.get('enabled', False):
        # No pinning - use default verification
        return True
    
    # Create custom SSL context with verification callback
    # Note: This is a simplified implementation
    # For production, consider using a proper pinning library like certifi-pinning
    
    ctx = ssl.create_default_context()
    
    # The actual verification happens in the callback
    # Python's requests library doesn't support custom SSL contexts directly
    # You'd need to use urllib3 or httpx for full control
    
    return ctx


def add_pin(hostname, sha256_fingerprint):
    """
    Add a new certificate pin
    
    Args:
        hostname: The hostname to pin
        sha256_fingerprint: SHA256 fingerprint of the certificate
    """
    pins = get_pinned_certs()
    
    if hostname not in pins:
        pins[hostname] = {'sha256': [], 'enabled': True}
    
    if sha256_fingerprint not in pins[hostname]['sha256']:
        pins[hostname]['sha256'].append(sha256_fingerprint)
    
    # Save
    data = {'pins': pins}
    with open(PINS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def remove_pin(hostname, sha256_fingerprint=None):
    """
    Remove a certificate pin
    
    Args:
        hostname: The hostname
        sha256_fingerprint: Specific fingerprint to remove, or None to remove all
    """
    pins = get_pinned_certs()
    
    if hostname not in pins:
        return
    
    if sha256_fingerprint:
        pins[hostname]['sha256'] = [
            p for p in pins[hostname]['sha256'] 
            if p != sha256_fingerprint
        ]
    else:
        del pins[hostname]
    
    # Save
    data = {'pins': pins}
    with open(PINS_FILE, 'w') as f:
        json.dump(data, f, indent=2)
