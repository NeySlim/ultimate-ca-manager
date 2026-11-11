"""Node files kept in the database, so every node writes the same bytes to its disk."""
from utils.datetime_utils import utc_now

KERBEROS_KEYTAB = 'kerberos.keytab'
# The self-signed HTTPS pair regenerated in HA, as JSON {"crt": pem, "key": pem}
HTTPS_GENERATED = 'https.generated'


def store_file(name, data: bytes, actor=None):
    """Store ``data`` under ``name`` in the caller's transaction (the caller commits)."""
    from models import SharedFile, db
    from utils.key_codec import store_pem_bytes
    row = db.session.get(SharedFile, name)
    if row is None:
        row = SharedFile(name=name)
        db.session.add(row)
    row.content = store_pem_bytes(data)
    row.updated_at = utc_now()
    row.updated_by = actor
    return row


def read_file(name):
    """The stored bytes, or None. Raises ValueError when they cannot be decrypted here."""
    from models import SharedFile, db
    from utils.key_codec import load_pem_bytes
    row = db.session.get(SharedFile, name)
    if row is None:
        return None
    return load_pem_bytes(row.content, context=f"shared file {name}")


def drop_file(name):
    """Remove ``name`` in the caller's transaction; True when a row was there."""
    from models import SharedFile, db
    row = db.session.get(SharedFile, name)
    if row is None:
        return False
    db.session.delete(row)
    return True

