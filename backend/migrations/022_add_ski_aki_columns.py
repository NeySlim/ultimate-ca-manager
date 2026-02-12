"""
Migration 022: Add SKI/AKI columns for reliable certificate chain matching.

Subject Key Identifier (SKI) on CAs and Authority Key Identifier (AKI) on
certificates provide cryptographically reliable chain linking, independent
of DN matching which can be ambiguous.

Also backfills existing records by extracting SKI/AKI from stored certificates.
"""

def upgrade(conn):
    import base64
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509.oid import ExtensionOID

    # Add columns if not present
    for table, col, col_type in [
        ('certificate_authorities', 'ski', 'VARCHAR(200)'),
        ('certificates', 'aki', 'VARCHAR(200)'),
        ('certificates', 'ski', 'VARCHAR(200)'),
    ]:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        if col not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")

    conn.commit()

    # --- Backfill existing records ---

    def extract_ski(cert_obj):
        try:
            ext = cert_obj.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
            return ext.value.key_identifier.hex(':').upper()
        except Exception:
            return None

    def extract_aki(cert_obj):
        try:
            ext = cert_obj.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
            if ext.value.key_identifier:
                return ext.value.key_identifier.hex(':').upper()
        except Exception:
            pass
        return None

    def load_cert(crt_b64):
        try:
            pem = base64.b64decode(crt_b64)
            if isinstance(pem, bytes):
                pem = pem.decode('utf-8')
            return x509.load_pem_x509_certificate(pem.encode(), default_backend())
        except Exception:
            return None

    # Backfill CAs
    rows = conn.execute("SELECT id, crt FROM certificate_authorities WHERE crt IS NOT NULL AND ski IS NULL").fetchall()
    for row in rows:
        cert_obj = load_cert(row[1])
        if cert_obj:
            ski = extract_ski(cert_obj)
            if ski:
                conn.execute("UPDATE certificate_authorities SET ski = ? WHERE id = ?", (ski, row[0]))

    # Backfill certificates
    rows = conn.execute("SELECT id, crt FROM certificates WHERE crt IS NOT NULL AND aki IS NULL").fetchall()
    for row in rows:
        cert_obj = load_cert(row[1])
        if cert_obj:
            aki = extract_aki(cert_obj)
            ski = extract_ski(cert_obj)
            conn.execute("UPDATE certificates SET aki = ?, ski = ? WHERE id = ?", (aki, ski, row[0]))

    conn.commit()


def downgrade(conn):
    # SQLite doesn't support DROP COLUMN easily
    pass
