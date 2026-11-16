from utils.encryption import SecretUnreadable
from . import bp
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from .helpers import ldap_auto_bind, ldap_bind, _get_ssl_verify, _cleanup_ssl_verify, _build_ldap_tls, _decrypt_ldap_password, _encrypt_ldap_password, _parse_json_field, _parse_group_list, _mapping_rules, group_match_key
import ldap3
from ldap3 import Server, Connection, ALL, Tls
from ldap3.utils.conv import escape_filter_chars
import ssl
import logging
import requests as http_requests
from utils.datetime_utils import utc_isoformat
from utils.dn_parse import get_dn_attribute, get_parent_dn, parse_dn, _unescape_value
from utils.ssrf_protection import (
    safe_request_head, validate_url_not_cloud_metadata)

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
        # An ldap3 Attribute: int() and comparisons need its value.
        uac = getattr(user_entry, 'userAccountControl', None)
        uac = getattr(uac, 'value', uac)
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
        uac_str = uac
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
            auto_bind=ldap_auto_bind(provider)
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
    except SecretUnreadable as e:
        # Names the secret, never its value
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"LDAP connection test failed: {e}")
        return error_response("LDAP connection failed. Check server address, port, and credentials.", 400)


# Returned when ``before_bind`` refused the entry: the user's password was not tried.
ATTEMPT_REFUSED = 'attempt_refused'
# Returned when the admission depends on groups the directory did not give.
GROUPS_UNREADABLE = 'groups_unreadable'
# Without a group filter, the membership clause alone selects the groups: an objectClass
# guess would drop the kinds it does not name (groupOfNames, groupOfUniqueNames, AD group).
DEFAULT_GROUP_FILTER = '(objectClass=*)'


class LdapGroupsUnreadable(Exception):
    """The directory did not answer a group read with success."""


def _admission_needs_groups(provider):
    return bool(_mapping_rules(provider)) or bool(_parse_group_list(provider.ldap_required_groups))


def _service_connection(provider, server):
    # check_names=False: attributes asked for may be missing from this server's schema
    # (objectGUID on OpenLDAP, entryUUID on AD); the server returns the ones it has.
    return ldap3.Connection(
        server,
        user=provider.ldap_bind_dn,
        password=_decrypt_ldap_password(provider),
        auto_bind=ldap_auto_bind(provider),
        check_names=False,
    )


def _dn_key(dn):
    return [sorted((t.casefold(), _unescape_value(v).strip().casefold()) for t, v in rdn)
            for rdn in parse_dn(dn)]


def _in_a_naming_context(server, dn):
    """Whether ``dn`` lies in a naming context the server publishes (RFC 4512 §5.1);
    a server that publishes none is given the benefit of the doubt."""
    contexts = getattr(getattr(server, 'info', None), 'naming_contexts', None) or []
    if isinstance(contexts, str):
        contexts = [contexts]
    keys = []
    for context in contexts:
        try:
            keys.append(_dn_key(str(context)))
        except ValueError:
            continue
    if not keys:
        return True
    target = _dn_key(dn)
    return any(key and len(key) <= len(target) and target[len(target) - len(key):] == key
               for key in keys)


def _ldap_group_search_bases(provider, server):
    """Bases tried in order: the explicit group base alone; else the parent of the base DN
    (where 2.x searched) when this server holds it, then the base DN itself."""
    explicit = (getattr(provider, 'ldap_group_base_dn', None) or '').strip()
    if explicit:
        return [explicit]
    base_dn = provider.ldap_base_dn
    try:
        parent = get_parent_dn(base_dn)
        if parent and _in_a_naming_context(server, parent):
            return [parent, base_dn]
    except ValueError:
        pass
    return [base_dn]


def _search_succeeded(conn, what):
    """Only a success result is an answer: noSuchObject, a referral or a limit is not."""
    result = conn.result or {}
    if result.get('result') != 0:
        raise LdapGroupsUnreadable(
            f"{what}: {result.get('description') or result.get('result')} "
            f"{result.get('message') or ''}".strip())


def _ldap_read_groups(provider, server, user_dn):
    """Names of the groups ``user_dn`` is a direct member of, the same for the login and
    the mapping test. Raises LdapGroupsUnreadable rather than answer an empty list."""
    member_attr = (provider.ldap_group_member_attr or 'member').strip().lower()
    try:
        conn = _service_connection(provider, server)
        try:
            if member_attr == 'memberof':
                # memberOf of the entry itself: any directory, no AD-only distinguishedName.
                conn.search(user_dn, '(objectClass=*)', search_scope=ldap3.BASE,
                            attributes=['memberOf'])
                _search_succeeded(conn, 'memberOf read')
                if not conn.entries:
                    raise LdapGroupsUnreadable('memberOf read: the user entry was not returned')
                entry = conn.entries[0]
                if not hasattr(entry, 'memberOf'):
                    return []
                values = entry.memberOf.values if hasattr(entry.memberOf, 'values') \
                    else [str(entry.memberOf)]
                groups = []
                for group_dn in values:
                    # One value that is no DN costs that group only, not the others.
                    try:
                        name = get_dn_attribute(str(group_dn), 'CN')
                    except ValueError:
                        logger.warning(f"LDAP memberOf value skipped, not a DN: {str(group_dn)[:200]!r}")
                        continue
                    if name is not None:
                        groups.append(name)
                return groups
            gf = (provider.ldap_group_filter or '').strip() or DEFAULT_GROUP_FILTER
            if not gf.startswith('('):
                gf = f'({gf})'
            group_filter = f'(&{gf}({member_attr}={escape_filter_chars(user_dn)}))'
            failures = []
            for base in _ldap_group_search_bases(provider, server):
                try:
                    conn.search(base, group_filter, search_scope=ldap3.SUBTREE, attributes=['cn'])
                    _search_succeeded(conn, f'group search under {base}')
                except (LdapGroupsUnreadable, ldap3.core.exceptions.LDAPOperationResult) as e:
                    failures.append(str(e) or type(e).__name__)
                    continue
                return [str(entry.cn) for entry in conn.entries if hasattr(entry, 'cn')]
            raise LdapGroupsUnreadable('; '.join(failures))
        finally:
            conn.unbind()
    except LdapGroupsUnreadable:
        raise
    except Exception as e:
        raise LdapGroupsUnreadable(str(e) or type(e).__name__) from e


def _ldap_entry_groups(provider, server, user_dn, username):
    """``(groups, error)``: read whenever the admission or the group filter asks for them."""
    if not (_admission_needs_groups(provider) or (provider.ldap_group_filter or '').strip()):
        return [], None
    try:
        groups = _ldap_read_groups(provider, server, user_dn)
    except LdapGroupsUnreadable as e:
        logger.warning(f"LDAP groups of {username} could not be read: {e}")
        return [], str(e)
    logger.info(f"LDAP groups for {username}: {groups}")
    return groups, None


def _ldap_entry_refusal(provider, user_entry, user_dn, safe_username, groups, groups_error):
    """The directory's reason to refuse this entry, or None; the mapping rules come after."""
    if _check_account_disabled(None, user_entry, user_dn, provider, safe_username):
        return 'account_disabled'
    if groups_error is not None and _admission_needs_groups(provider):
        return GROUPS_UNREADABLE
    group_list = _parse_group_list(provider.ldap_required_groups)
    if group_list:
        key = group_match_key(provider)
        user_groups = {key(g) for g in groups}
        if not any(key(g) in user_groups for g in group_list):
            logger.info(
                f"LDAP login denied for {safe_username}: not in required groups {group_list}, "
                f"user groups: {groups}"
            )
            return 'group_denied'
    return None


def _ldap_find_user(provider, server, username):
    """The directory entry the user filter finds for ``username``, or None."""
    conn = _service_connection(provider, server)
    try:
        user_filter = provider.ldap_user_filter.replace('{username}', escape_filter_chars(username))
        # All normal (*) and operational (+) attributes: the immutable id wherever it lives
        # (entryUUID on OpenLDAP, objectGUID on AD) and the disabled-check attributes.
        conn.search(provider.ldap_base_dn, user_filter, attributes=['*', '+'])
        return conn.entries[0] if conn.entries else None
    finally:
        conn.unbind()


def _ldap_entry_identity(provider, user_entry, username):
    """dn, stable uid, username, email and full name the directory entry carries."""
    stable_uid = None
    for attr in ([provider.ldap_uid_attr] if getattr(provider, 'ldap_uid_attr', None)
                 else ['objectGUID', 'entryUUID']):
        try:
            raw = getattr(user_entry, attr).value
        except Exception:
            raw = None
        if raw:
            stable_uid = raw.hex() if isinstance(raw, (bytes, bytearray)) else str(raw).strip()
            break
    return {
        'dn': user_entry.entry_dn,
        'uid': stable_uid,  # immutable id (None → matching falls back to dn/username)
        'username': str(getattr(user_entry, provider.ldap_username_attr, username)),
        'email': str(getattr(user_entry, provider.ldap_email_attr, '')),
        'fullname': str(getattr(user_entry, provider.ldap_fullname_attr, '')),
    }


def _ldap_authenticate_user(provider, username, password, before_bind=None):
    """Authenticate user via LDAP with proper filter escaping.

    ``before_bind(identity)`` runs once the entry is found and before the user's bind;
    a falsy answer returns (None, ATTEMPT_REFUSED) without trying the password."""
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

        # SECURITY: Escape username to prevent LDAP injection
        safe_username = escape_filter_chars(username)
        user_entry = _ldap_find_user(provider, server, username)
        if user_entry is None:
            return None, "Invalid credentials"
        user_dn = user_entry.entry_dn
        identity = _ldap_entry_identity(provider, user_entry, username)

        if before_bind is not None and not before_bind(dict(identity)):
            return None, ATTEMPT_REFUSED

        # Attempt to bind as the user to verify password
        user_conn = Connection(
            server,
            user=user_dn,
            password=password
        )

        if not ldap_bind(user_conn, provider):
            return None, "Invalid credentials"

        user_conn.unbind()

        groups, groups_error = _ldap_entry_groups(provider, server, user_dn, username)
        refusal = _ldap_entry_refusal(provider, user_entry, user_dn, safe_username,
                                      groups, groups_error)
        if refusal:
            return None, refusal

        return dict(identity, groups=groups), None

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
        # Through the pinning helper, and without following redirects.
        # `requests.head` does not follow them by default: this call asked
        # for it, and a redirect goes to a host the check above never saw,
        # since `pin_host` pins the host that was validated and only that
        # one. A 3xx already proves the endpoint answers, which is all a
        # reachability test needs. The helper also connects to the addresses
        # that were validated, closing the second lookup a bare `head` did.
        response = safe_request_head(provider.oauth2_auth_url, timeout=5,
                                     verify=verify)

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
