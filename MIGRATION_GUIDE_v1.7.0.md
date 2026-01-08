# Migration Guide: Fixing Issue #4 - Missing webauthn_credentials Table

## Problem

When upgrading from UCM v1.6.x to v1.7.x, you may encounter this error:

```
sqlite3.OperationalError: no such table: webauthn_credentials
```

This happens because v1.7.0 introduced WebAuthn/FIDO2 support, which requires new database tables.

## Solution

Run the migration script to add the missing tables.

### For Docker Deployments

#### Option 1: Using Docker Exec

```bash
# Enter the running container
docker exec -it <container-name> /bin/bash

# Run migration script
cd /app
python3 migrate_v1_7_0_auth.py

# Exit container
exit

# Restart container
docker restart <container-name>
```

#### Option 2: Using Docker Compose

```bash
# Enter container
docker-compose exec ucm /bin/bash

# Run migration
cd /app
python3 migrate_v1_7_0_auth.py

# Exit and restart
exit
docker-compose restart ucm
```

#### Option 3: Direct Command

```bash
docker exec <container-name> python3 /app/migrate_v1_7_0_auth.py
docker restart <container-name>
```

### For System Installations

```bash
cd /opt/ucm
sudo python3 migrate_v1_7_0_auth.py
sudo systemctl restart ucm
```

## What the Migration Does

The migration script adds:

### 1. New Columns to `users` Table
- `full_name` - User's full name
- `mfa_enabled` - Multi-factor authentication flag

### 2. New Table: `auth_certificates`
Stores client certificates for mTLS authentication:
- Certificate serial numbers
- Subject and issuer DN
- Fingerprints
- Validity periods

### 3. New Table: `webauthn_credentials`
Stores FIDO2/WebAuthn security keys:
- Credential IDs
- Public keys
- Sign counters (replay protection)
- Authenticator metadata
- Backup status

### 4. New Table: `webauthn_challenges`
Temporary challenges for WebAuthn flows:
- Registration challenges
- Authentication challenges
- Expiration tracking

### 5. System Configuration
- `cert_auth_enabled` - Enable mTLS authentication
- `cert_auth_required` - Require certificate (no password)
- `mfa_required_for_admins` - Enforce MFA for admins
- `webauthn_enabled` - Enable WebAuthn/FIDO2

## Verification

After running the migration, verify the tables exist:

### Docker

```bash
docker exec <container-name> sqlite3 /app/data/ucm.db ".tables"
```

You should see:
```
webauthn_credentials
webauthn_challenges
auth_certificates
```

### System Install

```bash
sqlite3 /opt/ucm/data/ucm.db ".tables"
```

## Troubleshooting

### Permission Denied

**Docker:**
```bash
# Run as root
docker exec -u root <container-name> python3 /app/migrate_v1_7_0_auth.py
```

**System:**
```bash
# Use sudo
sudo python3 /opt/ucm/migrate_v1_7_0_auth.py
```

### Database Locked

Stop the application first:

**Docker:**
```bash
docker stop <container-name>
docker run --rm -v ucm-data:/app/data <image> python3 /app/migrate_v1_7_0_auth.py
docker start <container-name>
```

**System:**
```bash
sudo systemctl stop ucm
sudo python3 /opt/ucm/migrate_v1_7_0_auth.py
sudo systemctl start ucm
```

### Migration Already Run

The script is safe to run multiple times. It uses `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE IF NOT EXISTS` to avoid errors.

### Backup First (Recommended)

**Docker:**
```bash
# Backup database
docker cp <container-name>:/app/data/ucm.db ./ucm_backup_$(date +%Y%m%d).db
```

**System:**
```bash
# Backup database
sudo cp /opt/ucm/data/ucm.db /opt/ucm/data/ucm_backup_$(date +%Y%m%d).db
```

## Alternative: Fresh Database

If migration fails, you can recreate the database (⚠️ **DELETES ALL DATA**):

**Docker:**
```bash
docker stop <container-name>
docker volume rm ucm-data  # or delete persistent volume
docker start <container-name>
```

**System:**
```bash
sudo systemctl stop ucm
sudo rm /opt/ucm/data/ucm.db
sudo systemctl start ucm
```

This will create a fresh database with all v1.7.0 tables.

## Prevention for Future Updates

To prevent this issue in future updates:

### 1. Use Docker with Proper Versioning

```yaml
# docker-compose.yml
services:
  ucm:
    image: neyslim/ultimate-ca-manager:1.7.2
    # Don't use :latest - pin specific versions
```

### 2. Read Release Notes

Always check the [CHANGELOG](https://github.com/NeySlim/ultimate-ca-manager/blob/main/CHANGELOG.md) before upgrading.

### 3. Run Migrations After Upgrade

If release notes mention database changes, run the migration script.

### 4. Backup Before Upgrading

```bash
# Docker
docker exec <container-name> sqlite3 /app/data/ucm.db ".backup /app/data/backup.db"

# System
sudo sqlite3 /opt/ucm/data/ucm.db ".backup /opt/ucm/data/backup.db"
```

## Related Issues

- #2 - Database initialization race condition (fixed in v1.7.1)
- #3 - Missing webauthn dependencies (fixed in v1.7.2)

## Need Help?

If the migration fails or you encounter other issues:

1. Check logs: `docker logs <container-name>` or `journalctl -u ucm`
2. Open an issue: https://github.com/NeySlim/ultimate-ca-manager/issues
3. Include:
   - UCM version (before and after upgrade)
   - Database table list
   - Migration script output
   - Error messages

## See Also

- [Installation Guide](INSTALLATION.md)
- [Upgrade Guide](upgrade.sh)
- [Docker Documentation](DOCKERHUB_README.md)
