# User Management

**Version:** 1.8.2

## Overview

Manage UCM users, roles, and permissions.

## User Roles

### Administrator
- Full system access
- Create/delete users
- Manage all CAs and certificates
- System configuration

### Operator  
- Create certificates
- Revoke certificates
- View all resources
- Cannot modify system settings

### Viewer
- Read-only access
- View certificates, CAs, CRLs
- Cannot create or modify

## Creating Users

1. **Navigate to Users**
   - Admin → User Management

2. **Add User**
   - Click "Create User"
   - Enter:
     - Username
     - Email
     - Password
     - Role
   - ☑ Require password change on first login

3. **Save**
   - User receives email (if configured)
   - Can login immediately

## Multi-Factor Authentication

Users can enable:
- **WebAuthn** - Security keys ([WebAuthn-Support](WebAuthn-Support))
- **mTLS** - Client certificates ([MTLS-Authentication](MTLS-Authentication))

Configure in User Settings → Security.

## API Access

Generate API tokens:
1. User → My Account → API Tokens
2. Click "Generate Token"
3. Set expiration (90 days recommended)
4. Copy token (shown once!)

Use with API:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://ucm.example.com/api/v1/cas
```

See [API-Reference](API-Reference) for details.
