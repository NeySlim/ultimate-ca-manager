"""
Safe HTTP session factory.

Provides a convenience wrapper for creating requests.Session objects
with SSL warnings disabled.
"""
import requests
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

disable_warnings(InsecureRequestWarning)


def create_session(verify_ssl=False):
    """Create a pre-configured requests.Session."""
    session = requests.Session()
    session.verify = verify_ssl
    return session
