"""
Migration 008: Update CDP/OCSP URLs to use HTTP protocol

When the HTTP protocol server is enabled (port > 0), CDP and OCSP URLs
should use http:// instead of https:// to avoid TLS verification loops.
This migration converts existing URLs from https:// to http:// with the
configured HTTP protocol port.
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


def upgrade(conn):
    http_port = _get_http_port(conn)
    if http_port <= 0:
        return

    cas = conn.execute(
        "SELECT id, cdp_url, ocsp_url FROM certificate_authorities "
        "WHERE cdp_url IS NOT NULL OR ocsp_url IS NOT NULL"
    ).fetchall()

    for ca_id, cdp_url, ocsp_url in cas:
        updates = {}
        if cdp_url and cdp_url.startswith('https://'):
            # Extract hostname from URL: https://host:port/path -> host
            try:
                after_scheme = cdp_url[8:]  # after "https://"
                host_port = after_scheme.split('/')[0]
                hostname = host_port.split(':')[0]
                path = '/' + '/'.join(after_scheme.split('/')[1:]) if '/' in after_scheme else ''
                port_suffix = '' if http_port == 80 else f':{http_port}'
                updates['cdp_url'] = f'http://{hostname}{port_suffix}{path}'
            except Exception:
                pass

        if ocsp_url and ocsp_url.startswith('https://'):
            try:
                after_scheme = ocsp_url[8:]
                host_port = after_scheme.split('/')[0]
                hostname = host_port.split(':')[0]
                path = '/' + '/'.join(after_scheme.split('/')[1:]) if '/' in after_scheme else ''
                port_suffix = '' if http_port == 80 else f':{http_port}'
                updates['ocsp_url'] = f'http://{hostname}{port_suffix}{path}'
            except Exception:
                pass

        if updates:
            set_clause = ', '.join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [ca_id]
            conn.execute(
                f"UPDATE certificate_authorities SET {set_clause} WHERE id = ?",
                values
            )

    conn.commit()


def downgrade(conn):
    # Cannot reliably reverse - HTTPS port may vary
    pass
