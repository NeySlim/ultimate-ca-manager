from . import bp
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from .helpers import _get_ssl_verify, _cleanup_ssl_verify, _build_ldap_tls, _decrypt_ldap_password, _encrypt_ldap_password, _parse_json_field
import ldap3
from ldap3 import Server, Connection, ALL, Tls
from ldap3.utils.conv import escape_filter_chars
import ssl
import logging
import requests as http_requests
from utils.datetime_utils import utc_isoformat
from utils.ssrf_protection import validate_url_not_cloud_metadata

logger = logging.getLogger(__name__)


def _check_account_disabled(conn, user_entry, user_dn, provider, safe_username):
    """Check if the LDAP user account is disabled.

    AD: checks userAccountControl bit 2 (ACCOUNTDISABLE = 2).
    OpenLDAP: checks accountStatus attribute (value 'inactive' or 'negative').
    Also checks custom attribute if provider.account_status_attr is set.

    Returns True if the account is disabled, False otherwise.
    """
    try:
        # 1. Check custom attribute first (if explicitly configured)
        if provider.account_status_attr:
            attr_val = getattr(user_entry, provider.account_status_attr, None)
            if attr_val is not None:
                val = str(attr_val).lower().strip()
                if val in ('disabled', 'inactive', 'negative', 'no', '0'):
                    logger.info(f"LDAP account disabled via {provider.account_status_attr}={attr_val} for {safe_username}")
                    return True

        # 2. AD: check userAccountControl bit 2 (ACCOUNTDISABLE)
        uac = getattr(user_entry, 'userAccountControl', None)
        if uac is not None:
            try:
                uac_val = int(uac)
                # ACCOUNTDISABLE = 0x0002 (bit 2)
                if uac_val & 0x0002:
                    logger.info(f"AD account disabled (uac={uac_val}) for {safe_username}")
                    return True
            except (ValueError, TypeError):
                pass

        # 3. OpenLDAP: check accountStatus attribute
        #    Common values: 'active', 'inactive', 'negative', 'suspended'
        acct_status = getattr(user_entry, 'accountStatus', None)
        if acct_status is not None:
            status = str(acct_status).lower().strip()
            if status in ('inactive', 'negative', 'disabled', 'suspended'):
                logger.info(f"OpenLDAP account disabled (status={status}) for {safe_username}")
                return True

        # 4. Check for 'userAccountControl' string attribute (some LDAP servers)
        uac_str = getattr(user_entry, 'userAccountControl', None)
        if uac_str is not None and not isinstance(uac_str, int):
            val = str(uac_str).lower()
            if val in ('disabled', 'inactive', 'negative'):
                logger.info(f"LDAP account disabled (uac_str={val}) for {safe_username}")
                return True

    except Exception as e:
        logger.warning(f"Failed to check account disabled status for {safe_username}: {e}")

    return False


def _test_ldap_connection(provider):
    """Test LDAP connection"""
    try:
        import ldap3
        from ldap3 import Server, Connection, ALL, Tls
        from ldap3.utils.conv import escape_filter_chars

        tls_config = _build_ldap_tls(provider)
        server = Server(
            provider.ldap_server,
            port=provider.ldap_port,
            use_ssl=provider.ldap_use_ssl,
            tls=tls_config,
            get_info=ALL
        )

        conn = Connection(
            server,
            user=provider.ldap_bind_dn,
            password=_decrypt_ldap_password(provider),
            auto_bind=True
        )

        # Test search with escaped filter
        conn.search(
            provider.ldap_base_dn,
            '(objectClass=*)',
            attributes=['cn'],
            size_limit=1
        )

        conn.unbind()

        return success_response(data={
            'status': 'success',
            'message': 'LDAP connection successful',
            'server_info': str(server.info)[:500] if server.info else None
        })
    except ImportError:
        return error_response("LDAP library not installed. Run: pip install ldap3", 500)
    except Exception as e:
        logger.error(f"LDAP connection test failed: {e}")
        return error_response("LDAP connection failed. Check server address, port, and credentials.", 400)


def _ldap_authenticate_user(provider, username, password):
    """Authenticate user via LDAP with proper filter escaping"""
    try:
        import ldap3
        from ldap3 import Server, Connection, ALL, Tls
        from ldap3.utils.conv import escape_filter_chars

        tls_config = _build_ldap_tls(provider)
        server = Server(
            provider.ldap_server,
            port=provider.ldap_port,
            use_ssl=provider.ldap_use_ssl,
            tls=tls_config,
            get_info=ALL
        )

        # First bind as service account
        conn = Connection(
            server,
            user=provider.ldap_bind_dn,
            password=_decrypt_ldap_password(provider),
            auto_bind=True
        )

        # SECURITY: Escape username to prevent LDAP injection
        safe_username = escape_filter_chars(username)

        # Search for user with escaped filter
        user_filter = provider.ldap_user_filter.replace('{username}', safe_username)
        # Fetch disabled-check attributes so _check_account_disabled works
        extra_attrs = []
        if provider.account_status_attr:
            extra_attrs.append(provider.account_status_attr)
        conn.search(
            provider.ldap_base_dn,
            user_filter,
            attributes=list(set([
                provider.ldap_username_attr,
                provider.ldap_email_attr,
                provider.ldap_fullname_attr
            ] + extra_attrs))
        )

        if not conn.entries:
            conn.unbind()
            return None, "Invalid credentials"

        user_entry = conn.entries[0]
        user_dn = user_entry.entry_dn

        # Close service account connection
        conn.unbind()

        # Attempt to bind as the user to verify password
        user_conn = Connection(
            server,
            user=user_dn,
            password=password
        )

        if not user_conn.bind():
            return None, "Invalid credentials"

        user_conn.unbind()

        # Fetch user's groups for role mapping
        groups = []
        if provider.ldap_group_filter:
            member_attr = (provider.ldap_group_member_attr or 'member').strip().lower()
            try:
                if member_attr == 'memberof':
                    # Method: read memberOf attribute from user entry (AD style)
                    memberof_conn = Connection(
                        server,
                        user=provider.ldap_bind_dn,
                        password=_decrypt_ldap_password(provider),
                        auto_bind=True
                    )
                    safe_dn = escape_filter_chars(user_dn)
                    memberof_conn.search(
                        provider.ldap_base_dn,
                        f'(distinguishedName={safe_dn})',
                        attributes=['memberOf']
                    )
                    if not memberof_conn.entries:
                        # Fallback: search by user filter
                        safe_un = escape_filter_chars(username)
                        uf = provider.ldap_user_filter.replace('{username}', safe_un)
                        memberof_conn.search(provider.ldap_base_dn, uf, attributes=['memberOf'])

                    if memberof_conn.entries:
                        entry = memberof_conn.entries[0]
                        if hasattr(entry, 'memberOf'):
                            group_dns = entry.memberOf.values if hasattr(entry.memberOf, 'values') else [str(entry.memberOf)]
                            # Extract CN from each group DN
                            for gdn in group_dns:
                                gdn_str = str(gdn)
                                # Parse CN from DN like "CN=Grp_IT_ADM,OU=Groups,DC=example,DC=com"
                                for part in gdn_str.split(','):
                                    part = part.strip()
                                    if part.upper().startswith('CN='):
                                        groups.append(part[3:])
                                        break
                    memberof_conn.unbind()
                    logger.info(f"LDAP memberOf groups for {username}: {groups}")
                else:
                    # Method: search groups where member/uniqueMember = user_dn (OpenLDAP style)
                    group_conn = Connection(
                        server,
                        user=provider.ldap_bind_dn,
                        password=_decrypt_ldap_password(provider),
                        auto_bind=True
                    )
                    group_base = ','.join(provider.ldap_base_dn.split(',')[1:]) or provider.ldap_base_dn
                    # Ensure group_filter has parentheses
                    gf = provider.ldap_group_filter.strip()
                    if not gf.startswith('('):
                        gf = f'({gf})'
                    safe_dn = escape_filter_chars(user_dn)
                    group_filter = f'(&{gf}({member_attr}={safe_dn}))'
                    group_conn.search(group_base, group_filter, attributes=['cn'])
                    groups = [str(entry.cn) for entry in group_conn.entries if hasattr(entry, 'cn')]
                    group_conn.unbind()
                    logger.info(f"LDAP {member_attr} groups for {username}: {groups}")
            except Exception as e:
                logger.warning(f"Failed to fetch LDAP groups for {username}: {e}")

        # ── Check for disabled account ─────────────────────────────────────
        disabled = _check_account_disabled(
            conn, user_entry, user_dn, provider, safe_username
        )
        if disabled:
            conn.unbind()
            return None, 'account_disabled'

        # ── Check required groups (default-deny) ───────────────────────────
        required_groups = _parse_json_field(provider.ldap_required_groups or '{}')
        if required_groups:
            # Support both list and dict formats for backward compatibility
            if isinstance(required_groups, dict):
                group_list = list(required_groups.keys())
            elif isinstance(required_groups, list):
                group_list = required_groups
            else:
                group_list = []

            if group_list and groups:
                # Check if user belongs to ANY of the required groups
                allowed = any(g in groups for g in group_list)
                if not allowed:
                    logger.info(
                        f"LDAP login denied for {username}: not in required groups {group_list}, "
                        f"user groups: {groups}"
                    )
                    conn.unbind()
                    return None, 'group_denied'
            elif group_list and not groups:
                logger.info(
                    f"LDAP login denied for {username}: no groups fetched, "
                    f"required groups: {group_list}"
                )
                conn.unbind()
                return None, 'group_denied'

        # Return user info
        return {
            'dn': user_dn,
            'username': str(getattr(user_entry, provider.ldap_username_attr, username)),
            'email': str(getattr(user_entry, provider.ldap_email_attr, '')),
            'fullname': str(getattr(user_entry, provider.ldap_fullname_attr, '')),
            'groups': groups
        }, None

    except ImportError:
        return None, "LDAP library not installed"
    except Exception as e:
        logger.error(f"LDAP authentication error: {e}")
        return None, "LDAP authentication failed"


def _test_oauth2_connection(provider):
    """Test OAuth2 configuration (checks URLs are reachable)"""
    verify = _get_ssl_verify(provider, 'oauth2')
    # Narrow SSRF guard — admins legitimately point at internal Keycloak/IdP
    # on RFC1918 networks, so only block cloud metadata + loopback.
    try:
        validate_url_not_cloud_metadata(provider.oauth2_auth_url)
    except ValueError:
        _cleanup_ssl_verify(verify)
        return error_response("Authorization URL cannot target cloud metadata or loopback", 400)
    try:
        response = http_requests.head(provider.oauth2_auth_url, timeout=5, allow_redirects=True, verify=verify)

        return success_response(data={
            'status': 'success',
            'message': 'OAuth2 endpoints reachable',
            'auth_url_status': response.status_code
        })
    except http_requests.exceptions.SSLError as e:
        logger.error(f"OAuth2 connection test SSL error: {e}")
        return error_response(
            "SSL certificate verification failed. Enable 'Skip SSL Verification' or upload the CA certificate.", 400)
    except Exception as e:
        logger.error(f"OAuth2 connection test failed: {e}")
        return error_response("OAuth2 test failed. Check authorization URL is reachable.", 400)
    finally:
        _cleanup_ssl_verify(verify)


def _test_saml_connection(provider):
    """Test SAML configuration"""
    # For SAML, we mainly verify the certificate is valid
    if not provider.saml_certificate:
        return error_response("SAML certificate not configured", 400)

    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend

        # Try to parse certificate
        cert_pem = provider.saml_certificate
        if not cert_pem.startswith('-----BEGIN'):
            cert_pem = f"-----BEGIN CERTIFICATE-----\n{cert_pem}\n-----END CERTIFICATE-----"

        cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())

        return success_response(data={
            'status': 'success',
            'message': 'SAML certificate valid',
            'cert_subject': cert.subject.rfc4514_string(),
            'cert_expires': utc_isoformat(cert.not_valid_after_utc)
        })
    except Exception as e:
        logger.error(f"SAML certificate validation failed: {e}")
        return error_response("SAML certificate is invalid or malformed", 400)


# ============ Test Mapping (Dry Run) ============
