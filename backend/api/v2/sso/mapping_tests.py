from . import bp
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models.sso import SSOProvider
from .helpers import _parse_json_field, _resolve_role_from_mapping, _resolve_role, _check_ldap_lockout, _clear_ldap_failed_attempts


@bp.route('/api/v2/sso/providers/<int:provider_id>/test-mapping', methods=['POST'])
@require_auth(['write:sso'])
def test_mapping(provider_id):
    """Dry-run LDAP group lookup: fetches groups for a username without creating a session"""
    provider = SSOProvider.query.get_or_404(provider_id)

    if provider.provider_type != 'ldap':
        return error_response("Test mapping is only available for LDAP providers", 400)

    data = request.get_json() or {}
    test_username = data.get('username', '').strip()
    if not test_username:
        return error_response("Username is required", 400)

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

        safe_username = escape_filter_chars(test_username)
        user_filter = provider.ldap_user_filter.replace('{username}', safe_username)

        attrs = [
            provider.ldap_username_attr,
            provider.ldap_email_attr,
            provider.ldap_fullname_attr
        ]
        member_attr = (provider.ldap_group_member_attr or 'member').strip().lower()
        if member_attr == 'memberof':
            attrs.append('memberOf')

        conn.search(provider.ldap_base_dn, user_filter, attributes=attrs)

        if not conn.entries:
            conn.unbind()
            return success_response(data={
                'found': False,
                'message': f'User "{test_username}" not found in LDAP'
            })

        user_entry = conn.entries[0]
        user_dn = user_entry.entry_dn

        # Fetch groups
        groups = []
        if provider.ldap_group_filter:
            if member_attr == 'memberof':
                if hasattr(user_entry, 'memberOf'):
                    group_dns = user_entry.memberOf.values if hasattr(user_entry.memberOf, 'values') else [str(user_entry.memberOf)]
                    for gdn in group_dns:
                        gdn_str = str(gdn)
                        for part in gdn_str.split(','):
                            part = part.strip()
                            if part.upper().startswith('CN='):
                                groups.append(part[3:])
                                break
                else:
                    # Fallback: re-search with memberOf attribute
                    safe_dn = escape_filter_chars(user_dn)
                    conn.search(provider.ldap_base_dn, f'(distinguishedName={safe_dn})', attributes=['memberOf'])
                    if conn.entries and hasattr(conn.entries[0], 'memberOf'):
                        group_dns = conn.entries[0].memberOf.values if hasattr(conn.entries[0].memberOf, 'values') else [str(conn.entries[0].memberOf)]
                        for gdn in group_dns:
                            gdn_str = str(gdn)
                            for part in gdn_str.split(','):
                                part = part.strip()
                                if part.upper().startswith('CN='):
                                    groups.append(part[3:])
                                    break
            else:
                group_base = ','.join(provider.ldap_base_dn.split(',')[1:]) or provider.ldap_base_dn
                gf = provider.ldap_group_filter.strip()
                if not gf.startswith('('):
                    gf = f'({gf})'
                safe_dn = escape_filter_chars(user_dn)
                group_filter = f'(&{gf}({member_attr}={safe_dn}))'
                conn.search(group_base, group_filter, attributes=['cn'])
                groups = [str(entry.cn) for entry in conn.entries if hasattr(entry, 'cn')]

        conn.unbind()

        # Resolve role using same logic as real login
        resolved_role = _resolve_role(provider, {'groups': groups})

        return success_response(data={
            'found': True,
            'user_dn': user_dn,
            'username': str(getattr(user_entry, provider.ldap_username_attr, test_username)),
            'email': str(getattr(user_entry, provider.ldap_email_attr, '')),
            'groups': groups,
            'resolved_role': resolved_role,
            'role_mapping': _parse_json_field(provider.role_mapping) or {},
            'default_role': provider.default_role
        })

    except ImportError:
        return error_response("LDAP library not installed", 500)
    except Exception as e:
        logger.error(f"LDAP test mapping failed: {e}")
        return error_response(f"Test mapping failed: check LDAP configuration", 400)


# ============ SSO Sessions ============
