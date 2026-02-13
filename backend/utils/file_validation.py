"""File upload validation utilities for security."""
from werkzeug.utils import secure_filename
from pathlib import Path

# Max upload size: 10MB
MAX_UPLOAD_SIZE = 10 * 1024 * 1024

CERT_EXTENSIONS = {'.pem', '.crt', '.cer', '.p12', '.pfx', '.p7b', '.der', '.key'}
JSON_EXTENSIONS = {'.json'}
BACKUP_EXTENSIONS = {'.zip', '.enc'}


def validate_upload(file, allowed_extensions=None, max_size=MAX_UPLOAD_SIZE):
    """Validate an uploaded file. Returns (data, safe_filename) or raises ValueError."""
    if not file or not file.filename:
        raise ValueError("No file provided")

    filename = secure_filename(file.filename)
    if not filename:
        raise ValueError("Invalid filename")

    if allowed_extensions:
        ext = Path(filename).suffix.lower()
        if ext not in allowed_extensions:
            raise ValueError(f"Invalid file type: {ext}")

    data = file.read(max_size + 1)
    if len(data) > max_size:
        raise ValueError(f"File too large (max {max_size // (1024*1024)}MB)")

    return data, filename
