"""
CAs Management Routes v2.0 - Package Wrapper

This file is kept for backward compatibility. The actual implementation
is now in the `cas/` package directory.

See: backend/api/v2/cas/__init__.py
"""

# Import the package to ensure routes are registered
from api.v2.cas import bp

# Re-export bp for backward compatibility
__all__ = ['bp']
