"""
Migration 007: Migrate CDP URLs from numeric IDs to refid (UUID)

Changes /cdp/{numeric_id}.crl to /cdp/{refid}.crl to prevent
sequential ID enumeration (security improvement).
Backwards-compatible: the CDP route handler accepts both formats.
"""


def upgrade(conn):
    # Get all CAs with CDP URLs containing numeric IDs
    cas = conn.execute(
        "SELECT id, refid, cdp_url FROM certificate_authorities WHERE cdp_url IS NOT NULL"
    ).fetchall()

    for ca_id, refid, cdp_url in cas:
        if not cdp_url or not refid:
            continue
        # Replace /cdp/{id}.crl with /cdp/{refid}.crl
        old_pattern = f"/cdp/{ca_id}.crl"
        new_pattern = f"/cdp/{refid}.crl"
        if old_pattern in cdp_url:
            new_url = cdp_url.replace(old_pattern, new_pattern)
            conn.execute(
                "UPDATE certificate_authorities SET cdp_url = ? WHERE id = ?",
                (new_url, ca_id)
            )
        # Also fix delta CRL pattern
        old_delta = f"/cdp/{ca_id}-delta.crl"
        new_delta = f"/cdp/{refid}-delta.crl"
        # Delta CRL URLs are generated dynamically, not stored, so no DB update needed

    conn.commit()


def downgrade(conn):
    # Revert to numeric IDs
    cas = conn.execute(
        "SELECT id, refid, cdp_url FROM certificate_authorities WHERE cdp_url IS NOT NULL"
    ).fetchall()

    for ca_id, refid, cdp_url in cas:
        if not cdp_url or not refid:
            continue
        old_pattern = f"/cdp/{refid}.crl"
        new_pattern = f"/cdp/{ca_id}.crl"
        if old_pattern in cdp_url:
            new_url = cdp_url.replace(old_pattern, new_pattern)
            conn.execute(
                "UPDATE certificate_authorities SET cdp_url = ? WHERE id = ?",
                (new_url, ca_id)
            )

    conn.commit()
