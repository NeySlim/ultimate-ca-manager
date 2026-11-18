"""
WSGI entry point for Gunicorn
"""
import sys
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from startup_refusal import EXIT_CODE, DatabaseRefused  # noqa: E402
from app import create_app  # noqa: E402

# Create Flask application instance; a refused database exits with a code of its own,
# which gunicorn (it catches RuntimeError alone, as exit 1) passes on
try:
    app = create_app()
except DatabaseRefused as exc:
    print(f"\nError: {exc}\n", file=sys.stderr)
    sys.exit(EXIT_CODE)

if __name__ == "__main__":
    app.run()
