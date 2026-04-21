"""Safe HTTP session factory."""
import requests
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning


def create_session(verify_ssl=True):
    """Create a pre-configured requests.Session.

    verify_ssl defaults to True. Callers handling private/self-signed
    infrastructure can opt out explicitly with verify_ssl=False.
    """
    session = requests.Session()
    session.verify = verify_ssl
    if not verify_ssl:
        disable_warnings(InsecureRequestWarning)
    return session
