from . import bp
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models.sso import SSOProvider
from .helpers import _parse_json_field, _parse_group_list, _resolve_mapped_roles, _resolve_role, sso_admission, _mapping_rules, _build_ldap_tls
from . import connection_tests
import logging
from models import db

logger = logging.getLogger(__name__)

# What the dry run cannot decide: the login may still refuse on these.
NOT_CHECKED = ("Not checked by this test: the password, and the UCM account the sign-in would "
               "open (an account of the same name that this identity may not open, "
               "an account disabled in UCM, automatic account creation turned off, an e-mail that "
               "belongs to an account of another provider or left without one).")


@bp.route('/api/v2/sso/providers/<int:provider_id>/test-mapping', methods=['POST'])
@require_auth(['write:sso'])
def test_mapping(provider_id):
    """Dry run of an LDAP login past the password: the same entry, groups and verdict."""
    provider = db.get_or_404(SSOProvider, provider_id)

    if provider.provider_type != 'ldap':
        return error_response("Test mapping is only available for LDAP providers", 400)

    data = request.get_json() or {}
    test_username = data.get('username', '').strip()
    if not test_username:
        return error_response("Username is required", 400)

    try:
        import ldap3
        from ldap3.utils.conv import escape_filter_chars

        server = ldap3.Server(
            provider.ldap_server,
            port=provider.ldap_port,
            use_ssl=provider.ldap_use_ssl,
            tls=_build_ldap_tls(provider),
            get_info=ldap3.ALL
        )
        user_entry = connection_tests._ldap_find_user(provider, server, test_username)
        if user_entry is None:
            return success_response(data={
                'found': False,
                'message': f'User "{test_username}" not found in LDAP'
            })
        user_dn = user_entry.entry_dn
        identity = connection_tests._ldap_entry_identity(provider, user_entry, test_username)
        groups, groups_error = connection_tests._ldap_entry_groups(
            provider, server, user_dn, test_username)
        refusal = connection_tests._ldap_entry_refusal(
            provider, user_entry, user_dn, escape_filter_chars(test_username), groups, groups_error)
        external = dict(identity, groups=groups)
        if refusal is None and not sso_admission(provider, external):
            refusal = 'unmapped' if _mapping_rules(provider) else 'no_default_role'

        resolved_role = resolved_custom = None
        if refusal is None:
            mapped_role, mapped_custom = _resolve_mapped_roles(provider, external)
            resolved_role = _resolve_role(provider, external, mapped=mapped_role)
            resolved_custom = mapped_custom.name if mapped_custom else None

        return success_response(data={
            'found': True,
            'user_dn': user_dn,
            'username': identity['username'],
            'email': identity['email'],
            'groups': groups,
            'groups_readable': groups_error is None,
            'refusal': refusal,
            'access_allowed': refusal is None,
            'resolved_role': resolved_role,
            'resolved_custom_role': resolved_custom,
            'role_mapping': _parse_json_field(provider.role_mapping) or {},
            'default_role': provider.default_role,
            'required_groups': _parse_group_list(provider.ldap_required_groups),
            'account_checked': False,
            'note': NOT_CHECKED,
        })

    except ImportError:
        return error_response("LDAP library not installed", 500)
    except Exception as e:
        logger.error(f"LDAP test mapping failed: {e}")
        return error_response("Test mapping failed: check LDAP configuration", 400)


# ============ SSO Sessions ============
