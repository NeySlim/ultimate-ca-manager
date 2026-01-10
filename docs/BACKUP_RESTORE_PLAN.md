# Backup/Restore Architecture Plan - v1.8.4

**Goal:** Portable, technology-agnostic backup system inspired by UniFi/OPNsense

---

## 🎯 Design Principles

### 1. **Portable Format**
- Single encrypted archive file (`.ucm-backup`)
- JSON metadata + Base64-encoded binaries
- Technology-independent (works across SQLite → PostgreSQL migration)

### 2. **Complete System State**
- All CAs (certificates, keys, chains)
- All certificates (issued, revoked)
- CRLs and OCSP responses
- Users and roles
- System configuration
- Email settings
- ACME/SCEP/WebAuthn config

### 3. **Security First**
- AES-256-GCM encryption
- Password-based key derivation (PBKDF2)
- Private keys double-encrypted
- Optional GPG encryption

### 4. **Technology Agnostic**
- Database-independent format (JSON)
- Can restore to different DB backend
- Can restore to different server
- Version-aware (supports upgrades)

---

## 📦 Backup File Structure

### Format: `.ucm-backup` (encrypted JSON archive)

```json
{
  "metadata": {
    "version": "1.8.4",
    "database_type": "sqlite",
    "created_at": "2026-01-10T18:00:00Z",
    "hostname": "ucm.example.com",
    "backup_type": "full",
    "ucm_version": "1.8.4",
    "format_version": "1.0"
  },
  
  "configuration": {
    "system": {
      "fqdn": "ucm.example.com",
      "https_port": 8443,
      "session_timeout": 3600,
      "jwt_expiration": 86400
    },
    "acme": {
      "enabled": true,
      "directory_url": "https://ucm.example.com/acme/directory"
    },
    "scep": {
      "enabled": true
    },
    "smtp": {
      "enabled": true,
      "server": "smtp.gmail.com",
      "port": 587,
      "username": "alerts@example.com",
      "from_address": "noreply@ucm.example.com"
      // Password excluded for security
    },
    "notifications": {
      "expiration_warning_days": [30, 7, 1]
    }
  },
  
  "users": [
    {
      "username": "admin",
      "email": "admin@example.com",
      "full_name": "Administrator",
      "role": "admin",
      "created_at": "2026-01-01T00:00:00Z",
      "password_hash": "$2b$12$...",
      "webauthn_credentials": [
        {
          "credential_id": "base64...",
          "public_key": "base64...",
          "sign_count": 42,
          "device_name": "YubiKey 5"
        }
      ]
    }
  ],
  
  "certificate_authorities": [
    {
      "refid": "ca-root-001",
      "name": "Root CA",
      "type": "root",
      "subject": {
        "CN": "Root CA",
        "O": "Example Corp",
        "C": "US"
      },
      "key_type": "RSA",
      "key_size": 4096,
      "valid_from": "2026-01-01T00:00:00Z",
      "valid_to": "2036-01-01T00:00:00Z",
      "serial": "1234567890",
      "crl_enabled": true,
      "crl_validity_days": 30,
      "ocsp_enabled": true,
      
      // Certificate PEM (public)
      "certificate_pem": "-----BEGIN CERTIFICATE-----\nMIID...\n-----END CERTIFICATE-----",
      
      // Private key (encrypted with backup password + CA-specific salt)
      "private_key_encrypted": {
        "algorithm": "AES-256-GCM",
        "salt": "base64...",
        "nonce": "base64...",
        "ciphertext": "base64..."
      },
      
      // CRL if exists
      "crl_pem": "-----BEGIN X509 CRL-----\n...\n-----END X509 CRL-----",
      
      // Chain for intermediate CAs
      "chain_pem": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
    }
  ],
  
  "certificates": [
    {
      "refid": "cert-001",
      "ca_refid": "ca-root-001",
      "cert_type": "server_cert",
      "subject": {
        "CN": "www.example.com",
        "O": "Example Corp"
      },
      "san_dns": ["www.example.com", "example.com"],
      "san_ip": ["192.168.1.100"],
      "serial": "9876543210",
      "valid_from": "2026-01-01T00:00:00Z",
      "valid_to": "2027-01-01T00:00:00Z",
      "revoked": false,
      "revocation_date": null,
      "revocation_reason": null,
      
      // Certificate PEM
      "certificate_pem": "-----BEGIN CERTIFICATE-----\nMIID...\n-----END CERTIFICATE-----",
      
      // Private key (encrypted)
      "private_key_encrypted": {
        "algorithm": "AES-256-GCM",
        "salt": "base64...",
        "nonce": "base64...",
        "ciphertext": "base64..."
      },
      
      // PKCS#12 for client certs (optional)
      "pkcs12_encrypted": "base64..."
    }
  ],
  
  "acme_accounts": [
    {
      "email": "acme@example.com",
      "account_url": "https://acme.example.com/account/123",
      "status": "valid",
      "key_pem": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
    }
  ],
  
  "checksum": {
    "algorithm": "SHA256",
    "value": "hex..."
  }
}
```

---

## 🔐 Encryption Scheme

### Three-Layer Security

#### Layer 1: Backup File Encryption
```
User Password → PBKDF2 (100k iterations) → Master Key (256-bit)
↓
Master Key + Salt + Nonce → AES-256-GCM → Encrypted JSON
```

#### Layer 2: Private Key Double Encryption
```
Each CA/Cert private key:
  Random Salt → Derive Key from Master Key
  ↓
  Per-Key Encryption with AES-256-GCM
```

#### Layer 3: Optional GPG Layer
```
Encrypted JSON → GPG Encryption with public key
↓
.ucm-backup.gpg (for offsite storage)
```

---

## 🔄 Backup Process

### UI Workflow

1. **Settings → System Settings → Database → Backup**
2. **Click "Create Backup"**
3. **Configure Backup:**
   ```
   ┌─────────────────────────────────────────┐
   │  Create System Backup                   │
   ├─────────────────────────────────────────┤
   │                                         │
   │  Backup Type:                           │
   │  ○ Full (Database + Certificates)       │
   │  ○ Database Only                        │
   │  ○ Certificates Only                    │
   │                                         │
   │  Include:                               │
   │  ☑ Certificate Authorities              │
   │  ☑ Certificates & Keys                  │
   │  ☑ Users & Roles                        │
   │  ☑ Configuration                        │
   │  ☑ ACME Accounts                        │
   │  ☐ Email Password (not recommended)     │
   │                                         │
   │  Encryption:                            │
   │  Password: [••••••••••]                 │
   │  Confirm:  [••••••••••]                 │
   │                                         │
   │  [ Cancel ]  [ Create Backup ]          │
   └─────────────────────────────────────────┘
   ```

4. **Download:** `ucm-backup-20260110-180000.ucm-backup` (encrypted)

### Backend Implementation

```python
# backend/services/backup_service.py

class BackupService:
    def create_backup(self, password: str, options: dict) -> bytes:
        """Create encrypted backup archive"""
        
        # 1. Gather data from database
        data = {
            'metadata': self._get_metadata(),
            'configuration': self._get_configuration(),
            'users': self._export_users(),
            'certificate_authorities': self._export_cas(),
            'certificates': self._export_certificates(),
            'acme_accounts': self._export_acme_accounts()
        }
        
        # 2. Encrypt private keys individually
        master_key = self._derive_master_key(password)
        data = self._encrypt_private_keys(data, master_key)
        
        # 3. Convert to JSON
        json_data = json.dumps(data, indent=2)
        
        # 4. Calculate checksum
        checksum = hashlib.sha256(json_data.encode()).hexdigest()
        data['checksum'] = {'algorithm': 'SHA256', 'value': checksum}
        
        # 5. Encrypt entire JSON
        encrypted = self._encrypt_with_master_key(json_data, master_key)
        
        return encrypted
```

---

## 🔄 Restore Process

### UI Workflow

1. **Settings → System Settings → Database → Restore**
2. **Upload Backup File**
3. **Restore Configuration:**
   ```
   ┌─────────────────────────────────────────┐
   │  Restore System Backup                  │
   ├─────────────────────────────────────────┤
   │                                         │
   │  Backup File:                           │
   │  ucm-backup-20260110-180000.ucm-backup  │
   │                                         │
   │  📊 Backup Information:                 │
   │  Version:      1.8.4                    │
   │  Created:      2026-01-10 18:00:00 UTC  │
   │  Database:     SQLite                   │
   │  Size:         2.5 MB                   │
   │                                         │
   │  Contains:                              │
   │  • 5 Certificate Authorities            │
   │  • 142 Certificates                     │
   │  • 3 Users                              │
   │  • System Configuration                 │
   │                                         │
   │  Restore Options:                       │
   │  ☑ Certificate Authorities              │
   │  ☑ Certificates & Keys                  │
   │  ☑ Users (merge with existing)          │
   │  ☑ Configuration                        │
   │                                         │
   │  Decryption Password: [••••••••••]      │
   │                                         │
   │  ⚠️  Warning: UCM will restart!         │
   │                                         │
   │  [ Cancel ]  [ Restore Backup ]         │
   └─────────────────────────────────────────┘
   ```

4. **Automatic Service Restart**
5. **Restore Complete**

### Backend Implementation

```python
# backend/services/restore_service.py

class RestoreService:
    def restore_backup(self, file_data: bytes, password: str, options: dict):
        """Restore from encrypted backup"""
        
        # 1. Decrypt backup file
        master_key = self._derive_master_key(password)
        json_data = self._decrypt_with_master_key(file_data, master_key)
        
        # 2. Parse and validate
        data = json.loads(json_data)
        self._validate_backup(data)
        
        # 3. Check version compatibility
        if not self._is_compatible_version(data['metadata']['ucm_version']):
            raise IncompatibleVersionError()
        
        # 4. Start transaction
        with db.session.begin():
            # Restore CAs
            if options.get('restore_cas'):
                self._restore_cas(data['certificate_authorities'], master_key)
            
            # Restore certificates
            if options.get('restore_certificates'):
                self._restore_certificates(data['certificates'], master_key)
            
            # Restore users (merge or replace)
            if options.get('restore_users'):
                self._restore_users(data['users'], merge=options.get('merge_users'))
            
            # Restore config
            if options.get('restore_config'):
                self._restore_configuration(data['configuration'])
        
        # 5. Signal service restart
        restart_signal_file = Path('/opt/ucm/backend/data/.restart_requested')
        restart_signal_file.touch()
        
        return True
```

---

## 🔀 Database Migration Support

### SQLite → PostgreSQL Example

```python
class DatabaseMigrator:
    def migrate_backup(self, backup_data: dict, target_db: str):
        """Migrate backup between database backends"""
        
        if target_db == 'postgresql':
            # Adjust data types
            for ca in backup_data['certificate_authorities']:
                # SQLite stores dates as text, PostgreSQL as timestamp
                ca['valid_from'] = parse_datetime(ca['valid_from'])
                ca['valid_to'] = parse_datetime(ca['valid_to'])
            
            # Adjust UUIDs
            for cert in backup_data['certificates']:
                if 'refid' not in cert:
                    cert['refid'] = str(uuid.uuid4())
        
        return backup_data
```

---

## 📋 Implementation Checklist

### Phase 1: Core Backup (2-3h)
- [ ] Create `BackupService` class
- [ ] Implement data export from all models
- [ ] JSON serialization with encryption
- [ ] Download endpoint `/api/backup/create`
- [ ] UI: Backup configuration modal

### Phase 2: Core Restore (2-3h)
- [ ] Create `RestoreService` class
- [ ] Upload endpoint `/api/backup/restore`
- [ ] Decryption and validation
- [ ] Database transaction restore
- [ ] UI: Restore modal with file upload

### Phase 3: Security & Validation (1-2h)
- [ ] Password strength validation
- [ ] Checksum verification
- [ ] Version compatibility checks
- [ ] Backup file size limits
- [ ] Rate limiting on restore

### Phase 4: Advanced Features (2-3h)
- [ ] List available backups
- [ ] Backup metadata display
- [ ] Selective restore (CAs only, certs only)
- [ ] Backup encryption with GPG key
- [ ] Automated backup scheduling

---

## 🧪 Testing Strategy

### Test Scenarios

1. **Basic Backup/Restore**
   - Create backup → Restore on same system → Verify identical state

2. **Cross-Version Restore**
   - Backup on v1.8.4 → Restore on v1.9.0 → Verify upgrade compatibility

3. **Database Migration**
   - Backup on SQLite → Restore to PostgreSQL → Verify data integrity

4. **Partial Restore**
   - Restore only CAs → Verify certificates excluded
   - Restore only users → Verify CAs unchanged

5. **Password Security**
   - Wrong password → Decryption fails gracefully
   - Weak password → Rejected with error

6. **Large Backups**
   - 1000+ certificates → Backup/restore < 30 seconds
   - File size < 10 MB for typical setup

---

## 📊 Storage Requirements

| Item | Count | Size per Item | Total |
|------|-------|---------------|-------|
| CA (with 4096-bit key) | 10 | 5 KB | 50 KB |
| Certificate (with 2048-bit key) | 1000 | 2 KB | 2 MB |
| User | 50 | 1 KB | 50 KB |
| Configuration | 1 | 10 KB | 10 KB |
| Metadata | 1 | 5 KB | 5 KB |
| **Total (uncompressed)** | | | **~2.5 MB** |
| **Total (gzip compressed)** | | | **~500 KB** |

---

## 🔗 API Endpoints

```python
# Create backup
POST /api/v1/backup/create
Content-Type: application/json
Authorization: Bearer {jwt_token}

{
  "password": "secure_password",
  "type": "full",
  "include": {
    "cas": true,
    "certificates": true,
    "users": true,
    "configuration": true
  }
}

Response: Binary file download

---

# List backups
GET /api/v1/backup/list
Authorization: Bearer {jwt_token}

Response:
{
  "backups": [
    {
      "filename": "ucm-backup-20260110-180000.ucm-backup",
      "created_at": "2026-01-10T18:00:00Z",
      "size": 524288,
      "version": "1.8.4"
    }
  ]
}

---

# Restore backup
POST /api/v1/backup/restore
Content-Type: multipart/form-data
Authorization: Bearer {jwt_token}

file: ucm-backup-20260110-180000.ucm-backup
password: secure_password
options: {
  "restore_cas": true,
  "restore_certificates": true,
  "restore_users": true,
  "merge_users": false,
  "restore_configuration": true
}

Response:
{
  "success": true,
  "message": "Restore completed. Service will restart in 3 seconds.",
  "restored": {
    "cas": 5,
    "certificates": 142,
    "users": 3
  }
}
```

---

## 🎯 Success Criteria

✅ **Must Have:**
- Single encrypted file backup
- Complete system state capture
- Password-protected encryption
- Database-agnostic restore
- UI for backup/restore
- Automatic service restart

✅ **Nice to Have:**
- GPG encryption option
- Scheduled automated backups
- Backup rotation (keep last N)
- Email backup to administrator
- Cloud storage integration (S3, etc.)

---

**Estimated Total Time:** 8-10 hours
**Target Version:** v1.8.4
**Priority:** High

