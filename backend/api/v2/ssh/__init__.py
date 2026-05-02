"""
SSH CAs package — assembles the blueprint by importing all route modules.
"""

from .helpers import bp
from . import crud, script_routes, krl  # noqa: F401 — registers routes

__all__ = ['bp']
