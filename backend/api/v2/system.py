"""
System Routes v2.0 - Package Wrapper

This file is kept for backward compatibility. The actual implementation
is now in the `system/` package directory.

See: backend/api/v2/system/__init__.py
"""

# Import the package to ensure routes are registered
from api.v2.system import bp

# Re-export bp for backward compatibility
__all__ = ['bp']
