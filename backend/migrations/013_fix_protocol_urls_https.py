"""
Migration 013: Fix protocol URLs that use https:// instead of http://

CDP, OCSP, and AIA CA Issuers URLs must use http:// with the HTTP protocol
port (default 8080), NOT https:// with the web UI port.

This fixes a regression where the AIA implementation (v2.101) could generate
URLs using the web UI origin (https://host:8443/) instead of the protocol
HTTP server (http://host:8080/).

Migration 008 fixed CDP/OCSP URLs previously, but those may have been
overwritten when AIA was enabled (migration 012), and AIA URLs were never
covered by migration 008.
"""
import os


def _get_http_port(conn):
    """Get configured HTTP protocol port."""
    row = conn.execute(
        "SELECT value FROM system_config WHERE key = 'http_protocol_port'"
    ).fetchone()
    if row and row[0]:
        try:
            port = int(row[0])
            if port > 0:
                return port
        except (ValueError, TypeError):
            pass
    env_port = os.environ.get('HTTP_PROTOCOL_PORT', '')
    if env_port:
        try:
            port = int(env_port)
            if port > 0:
                return port
        except (ValueError, TypeError):
            pass
    return 8080


def _fix_url(url, http_port):
    """Convert https:// URL to http:// with correct port. Returns None if no fix needed."""
    if not url or not url.startswith('https://'):
        return None
    try:
        after_scheme = url[8:]  # after "https://"
        host_port = after_scheme.split('/')[0]
        hostname = host_port.split(':')[0]
        path = '/' + '/'.join(after_scheme.split('/')[1:]) if '/' in after_scheme else ''
        port_suffix = '' if http_port == 80 else f':{http_port}'
        return f'http://{hostname}{port_suffix}{path}'
    except Exception:
        return None


def upgrade(conn):
    http_port = _get_http_port(conn)
    if http_port <= 0:
        return

    cas = conn.execute(
        "SELECT id, cdp_url, ocsp_url, aia_ca_issuers_url "
        "FROM certificate_authorities "
        "WHERE cdp_url IS NOT NULL OR ocsp_url IS NOT NULL "
        "OR aia_ca_issuers_url IS NOT NULL"
    ).fetchall()

    fixed = 0
    for ca_id, cdp_url, ocsp_url, aia_url in cas:
        updates = {}

        new_cdp = _fix_url(cdp_url, http_port)
        if new_cdp:
            updates['cdp_url'] = new_cdp

        new_ocsp = _fix_url(ocsp_url, http_port)
        if new_ocsp:
            updates['ocsp_url'] = new_ocsp

        new_aia = _fix_url(aia_url, http_port)
        if new_aia:
            updates['aia_ca_issuers_url'] = new_aia

        if updates:
            set_clause = ', '.join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [ca_id]
            conn.execute(
                f"UPDATE certificate_authorities SET {set_clause} WHERE id = ?",
                values
            )
            fixed += 1

    conn.commit()
    if fixed:
        print(f"  Migration 013: Fixed protocol URLs for {fixed} CA(s)")


def downgrade(conn):
    pass
