# UCM Pro Features

UCM Pro extends the Community Edition with enterprise-grade features for large deployments.

## Features Overview

| Feature | Community | Pro | Enterprise |
|---------|-----------|-----|------------|
| Certificate Management | ✅ | ✅ | ✅ |
| Multiple CAs | ✅ | ✅ | ✅ |
| ACME Protocol | ✅ | ✅ | ✅ |
| SCEP Protocol | ✅ | ✅ | ✅ |
| User Groups | ❌ | ✅ | ✅ |
| Custom RBAC Roles | ❌ | ✅ | ✅ |
| SSO (LDAP/OAuth2/SAML) | ❌ | ✅ | ✅ |
| HSM Integration | ❌ | ✅ | ✅ |
| Advanced Audit Logs | ❌ | ✅ | ✅ |
| Priority Support | ❌ | ✅ | ✅ |
| SLA Guarantee | ❌ | ❌ | ✅ |

---

## User Groups

Organize users into groups with shared permissions.

### Features
- Create unlimited groups
- Assign multiple users per group
- Define group-level permissions
- Role inheritance from group membership

### Default Groups
- **Administrators** - Full system access
- **Certificate Operators** - Manage certificates and CSRs
- **Auditors** - Read-only audit access

### API Endpoints
```
GET    /api/v2/groups           - List groups
POST   /api/v2/groups           - Create group
GET    /api/v2/groups/:id       - Get group details
PUT    /api/v2/groups/:id       - Update group
DELETE /api/v2/groups/:id       - Delete group
POST   /api/v2/groups/:id/members - Add member
DELETE /api/v2/groups/:id/members/:uid - Remove member
```

---

## Custom RBAC Roles

Define granular permissions beyond the built-in roles.

### Features
- Create custom roles with specific permissions
- Inherit from base roles (admin, operator, viewer)
- Granular permission control per resource type
- Role hierarchy with permission inheritance

### Default Custom Roles
- **Certificate Manager** - Full certificate lifecycle
- **CA Administrator** - CA and CRL management
- **Security Auditor** - Read-only compliance access

### Permission Categories
- Certificates: read, write, delete, revoke, renew
- CAs: read, write, delete, sign
- CSRs: read, write, delete, sign
- Users: read, write, delete
- Settings: read, write
- Audit: read
- HSM: read, write, delete
- SSO: read, write, delete

### API Endpoints
```
GET    /api/v2/rbac/roles       - List custom roles
POST   /api/v2/rbac/roles       - Create role
GET    /api/v2/rbac/roles/:id   - Get role details
PUT    /api/v2/rbac/roles/:id   - Update role
DELETE /api/v2/rbac/roles/:id   - Delete role
GET    /api/v2/rbac/permissions - List all permissions
```

---

## SSO Integration

Single Sign-On with enterprise identity providers.

### Supported Providers
- **LDAP/Active Directory** - Bind authentication with group sync
- **OAuth2/OIDC** - OpenID Connect with major providers
- **SAML 2.0** - Enterprise SAML federation

### Features
- Auto-create users on first SSO login
- Auto-update user info on each login
- Map SSO groups to UCM roles
- Multiple providers simultaneously
- Connection testing before enabling

### LDAP Configuration
```json
{
  "provider_type": "ldap",
  "ldap_server": "ldap.example.com",
  "ldap_port": 389,
  "ldap_use_ssl": true,
  "ldap_base_dn": "dc=example,dc=com",
  "ldap_bind_dn": "cn=admin,dc=example,dc=com",
  "ldap_user_filter": "(uid={username})"
}
```

### OAuth2 Configuration
```json
{
  "provider_type": "oauth2",
  "oauth2_client_id": "ucm-client",
  "oauth2_auth_url": "https://idp.example.com/oauth/authorize",
  "oauth2_token_url": "https://idp.example.com/oauth/token",
  "oauth2_userinfo_url": "https://idp.example.com/oauth/userinfo",
  "oauth2_scopes": ["openid", "profile", "email"]
}
```

### API Endpoints
```
GET    /api/v2/sso/providers    - List providers
POST   /api/v2/sso/providers    - Create provider
PUT    /api/v2/sso/providers/:id - Update provider
DELETE /api/v2/sso/providers/:id - Delete provider
POST   /api/v2/sso/providers/:id/test - Test connection
POST   /api/v2/sso/providers/:id/toggle - Enable/disable
GET    /api/v2/sso/available    - Public: available providers for login
```

---

## HSM Integration

Hardware Security Module support for secure key storage.

### Supported HSM Types
- **PKCS#11** - Local HSMs (SafeNet, Thales, SoftHSM)
- **AWS CloudHSM** - AWS managed HSM clusters
- **Azure Key Vault** - Azure managed key storage
- **Google Cloud KMS** - Google Cloud key management

### Features
- Store CA private keys in HSM
- Generate keys directly in HSM
- Key usage tracking and audit
- Connection health monitoring
- Multiple HSM providers

### PKCS#11 Configuration
```json
{
  "provider_type": "pkcs11",
  "pkcs11_library_path": "/usr/lib/softhsm/libsofthsm2.so",
  "pkcs11_slot_id": 0,
  "pkcs11_token_label": "UCM Token"
}
```

### AWS CloudHSM Configuration
```json
{
  "provider_type": "aws-cloudhsm",
  "aws_cluster_id": "cluster-xxxxx",
  "aws_region": "us-east-1",
  "aws_crypto_user": "cu_user"
}
```

### Key Types
- RSA (2048, 3072, 4096 bit)
- ECDSA (P-256, P-384, P-521)
- AES (128, 256 bit) for encryption

### API Endpoints
```
GET    /api/v2/hsm/providers    - List HSM providers
POST   /api/v2/hsm/providers    - Create provider
PUT    /api/v2/hsm/providers/:id - Update provider
DELETE /api/v2/hsm/providers/:id - Delete provider
POST   /api/v2/hsm/providers/:id/test - Test connection
GET    /api/v2/hsm/keys         - List all keys
POST   /api/v2/hsm/providers/:id/keys - Generate key
DELETE /api/v2/hsm/keys/:id     - Destroy key
GET    /api/v2/hsm/stats        - HSM statistics
```

---

## License Activation

### License Types
- **Community** - Free, open source features only
- **Pro** - All Pro features, single organization
- **Enterprise** - Pro + SLA, multi-tenant, priority support

### Activation
1. Purchase license at https://ucm.example.com/pricing
2. Receive license key via email
3. Place key in `/opt/ucm/data/license.key`
4. Restart UCM service
5. Pro features automatically unlock

### License API
```
GET /api/v2/license - Get current license info
```

### Response
```json
{
  "type": "pro",
  "features": ["groups", "rbac", "sso", "hsm"],
  "expires_at": "2027-01-01T00:00:00Z",
  "licensed_to": "Example Corp"
}
```

---

## Database Tables

Pro features use isolated tables prefixed with `pro_`:

```sql
-- Groups
pro_groups
pro_group_members

-- RBAC
pro_custom_roles
pro_role_permissions

-- SSO
pro_sso_providers
pro_sso_sessions

-- HSM
pro_hsm_providers
pro_hsm_keys
```

Tables are automatically created on first startup when Pro modules are available.

---

## Support

- Documentation: https://docs.ucm.example.com
- Community: https://github.com/NeySlim/ultimate-ca-manager/discussions
- Pro Support: support@ucm.example.com
- Enterprise SLA: enterprise@ucm.example.com
