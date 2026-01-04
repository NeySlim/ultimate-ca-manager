# ❓ FAQ - Frequently Asked Questions

---

## 🔐 Security and PKI

### What's the difference between Root CA and Intermediate CA?

**Root CA** (Root Authority):
- At the top of the PKI hierarchy
- Self-signed
- Long validity (20-30 years)
- **Must be stored offline** (cold storage)
- Used only to sign Intermediate CAs

**Intermediate CA** (Intermediate Authority):
- Signed by the Root CA
- Used for daily issuance
- Medium validity (5-10 years)
- Can be revoked without affecting other Intermediate CAs
- **Online**, accessible for issuance

**Why this separation?**
- Security: If Intermediate is compromised, only it gets revoked
- Root CA remains secure offline
- Allows creating CAs for different purposes

---

### Should I really store my Root CA offline?

**Yes, absolutely** for production PKI!

**Best practices**:
```
1. Create Root CA in UCM
2. Export immediately (PKCS#12 with strong password)
3. Backup to:
   - Encrypted USB drive → physical safe
   - HSM (Hardware Security Module)
   - Encrypted off-site backup
4. Create Intermediate CA(s)
5. DELETE Root CA from UCM (or dedicated offline server)
```

**For test/dev environments**:
- Keeping Root CA online is acceptable
- Clearly mark as "TEST" in the CN

---

### What key length should I use?

**2026 Recommendations**:

| Usage | Algorithm | Length | Comment |
|-------|-----------|--------|---------|
| Root CA | RSA | 4096 bits | Maximum security |
| Intermediate CA | RSA | 4096 bits | Security + compatibility |
| Server certificates | RSA | 2048 bits | Current standard |
| Server certificates | ECDSA | P-256 | Modern, faster |
| Client certificates | RSA | 2048 bits | Compatible everywhere |
| Code signing | RSA | 4096 bits | Maximum security |
| IoT/Embedded | ECDSA | P-256 | Low power consumption |

**ECDSA vs RSA**:
- ECDSA P-256 ≈ RSA 3072 (equivalent security)
- ECDSA faster, smaller keys
- But less compatible (older systems)

---

### What validity period for my certificates?

**Browser limits (2026)**:
- Maximum: **398 days** (13 months)
- Recommended: **90-180 days** (auto-renewal)

**CA certificates**:
- Root CA: 20-30 years
- Intermediate CA: 5-10 years

**Other certificates**:
- Web servers: 90-398 days
- Clients: 1-3 years
- Code signing: 1-3 years
- IoT: 1-5 years (depending on use case)

**Trend**: Increasingly shorter validity periods for security

---

## 🔄 SCEP

### SCEP vs manual enrollment, when to use what?

**Use SCEP when**:
- Many devices (>10)
- Mobile devices (iOS, Android)
- Automatic renewal desired
- MDM (Mobile Device Management) environment
- IoT / embedded devices
- Large-scale network deployment

**Manual enrollment when**:
- Few certificates (<10)
- Individual servers
- Need for strict control
- Certificates with custom configurations

---

### My iPhone rejects the SCEP profile, why?

**Common causes**:

1. **UCM certificate not trusted**
   ```
   Solution: First install Root CA on iOS
   Settings → General → VPN & Device Management → Install Profile
   ```

2. **URL with IP instead of FQDN**
   ```
   ❌ https://192.168.1.100:8443/scep/mobile
   ✅ https://pki.example.com:8443/scep/mobile
   ```

3. **Incorrect challenge password**
   ```
   Use "Generate enrollment URL" in UCM
   QR Code recommended to avoid typos
   ```

4. **HTTPS port not accessible**
   ```
   Test from Safari: https://pki.example.com:8443
   Check firewall
   ```

---

### SCEP automatic renewal doesn't work

**Checklist**:
- [ ] Auto-renewal enabled in SCEP endpoint
- [ ] Renewal window configured (e.g., 30 days)
- [ ] Device has network access to UCM
- [ ] UCM HTTPS certificate still valid
- [ ] SCEP logs: `/opt/ucm/logs/scep.log`

**Manual test**:
```bash
# Force immediate renewal
# Temporarily modify existing certificate validity
# to expire within <30 days
```

---

## 💾 Database

### SQLite or PostgreSQL?

**SQLite** (default):
- ✅ Simple installation
- ✅ No separate server
- ✅ Perfect for <2000 certificates
- ❌ Write locks in concurrent access
- ❌ Limited performance

**PostgreSQL**:
- ✅ High performance
- ✅ Concurrent writes
- ✅ Scalable (>100k certificates)
- ✅ Replication, advanced backups
- ❌ Separate server required

**Recommendation**:
- Dev/Test: SQLite
- Production <2000 certs: SQLite OK
- Production >2000 certs: PostgreSQL
- Enterprise: PostgreSQL

---

### How to migrate from SQLite to PostgreSQL?

See: [PostgreSQL Migration Guide](Migration-Guide#sqlite-to-postgresql)

**Summary**:
```bash
# Use docker-compose.postgres.yml
docker-compose -f docker-compose.postgres.yml up -d

# UCM automatically detects PostgreSQL
# Automatic data migration
```

---

### How often should I make backups?

**Recommendations**:

**Full backup**:
- Daily minimum
- Before any critical operation (upgrade, etc.)
- Retention: 7-30 days

**Root CA backup** (if online):
- After each modification
- Secure storage, multiple copies
- Regular restore testing

**Automatic with UCM**:
```bash
# UCM automatic daily backup
/opt/ucm/backups/ucm-backup-YYYY-MM-DD.db

# Configurable in Settings → System → Backup
```

---

## 🌐 Deployment

### Which port to use: 8443 or 443?

**8443** (UCM default):
- ✅ No root required
- ✅ Can coexist with other web server
- ❌ Less standard URL (https://host:8443)

**443** (standard HTTPS):
- ✅ Standard URL (https://host)
- ❌ Requires root or CAP_NET_BIND_SERVICE capability
- ❌ Conflicts with other web server

**Recommended solution**:
```
Reverse proxy (nginx, Traefik, HAProxy)
Internet:443 → Proxy → UCM:8443

Advantages:
- Standard URL
- Load balancing possible
- Rate limiting
- WAF (Web Application Firewall)
```

---

### UCM behind a reverse proxy?

**Yes, recommended configuration!**

**nginx example**:
```nginx
server {
    listen 443 ssl http2;
    server_name pki.example.com;
    
    ssl_certificate /etc/ssl/certs/pki.example.com.crt;
    ssl_certificate_key /etc/ssl/private/pki.example.com.key;
    
    location / {
        proxy_pass https://localhost:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**UCM configuration**:
```bash
# .env
PREFERRED_URL_SCHEME=https
FORCE_HTTPS=true
```

---

### Can UCM be deployed in high availability (HA)?

**Yes, with some considerations**:

**HA Architecture**:
```
                Load Balancer
                     |
        +------------+------------+
        |                         |
    UCM Node 1              UCM Node 2
        |                         |
        +------------+------------+
                     |
              PostgreSQL
          (with replication)
```

**Requirements**:
- PostgreSQL (not SQLite)
- Shared storage for `/data` (NFS, S3, etc.)
- External session store (Redis)
- Load balancer (HAProxy, nginx)

**Limitations**:
- Shared private keys (security)
- Increased complexity
- Overhead for <10k certs

**Recommendation**: 
- <10k certs: Single node + backups
- >10k certs: HA setup

---

## 🔧 Operations

### How to revoke a certificate urgently?

**Via UI** (recommended):
```
1. Certificates → Search (serial or CN)
2. Actions → Revoke
3. Reason: Key Compromise
4. Confirm

Immediate effect:
- Added to CRL
- OCSP responds "revoked"
```

**Via CLI** (if UI inaccessible):
```bash
cd /opt/ucm
source venv/bin/activate
python3 << EOF
from app import create_app, db
from app.models import Certificate
from app.services.certificate_service import revoke_certificate

app = create_app()
with app.app_context():
    cert = Certificate.query.filter_by(serial_number='1A2B3C4D').first()
    revoke_certificate(cert.id, reason='key_compromise')
    print(f"Certificate {cert.serial_number} revoked")
EOF
```

---

### The CRL is growing too large, what to do?

**Options**:

1. **Delta CRL** (not yet implemented in UCM v1.0.1)

2. **Purge old revocations**
   ```
   Settings → CRL → Auto-cleanup
   Remove revoked certificates expired for >90 days
   ```

3. **Reduce CRL lifetime**
   ```
   Next Update: 24h instead of 7 days
   But increases server load
   ```

4. **Prefer OCSP**
   ```
   Enable OCSP responder
   Modern clients prefer OCSP
   CRL as fallback only
   ```

---

### How to test my certificate?

**Web server test**:
```bash
# SSL Labs (online)
https://www.ssllabs.com/ssltest/analyze.html?d=example.com

# OpenSSL
openssl s_client -connect example.com:443 -showcerts

# Verify chain
openssl verify -CAfile chain.pem cert.pem
```

**OCSP test**:
```bash
openssl ocsp \
  -issuer intermediate-ca.pem \
  -cert cert.pem \
  -url http://ocsp.example.com:8080 \
  -CAfile root-ca.pem
```

**CRL test**:
```bash
curl http://pki.example.com:8080/crl/ca-123.crl -o crl.der
openssl crl -in crl.der -inform DER -text -noout
```

---

## 📱 Compatibility

### Which systems support SCEP?

**Natively supported**:
- ✅ iOS / iPadOS (all versions)
- ✅ macOS (10.7+)
- ✅ Android (with third-party app or MDM)
- ✅ Windows (via NDES/Intune)
- ✅ Cisco routers/switches
- ✅ Palo Alto firewalls
- ✅ Juniper devices
- ✅ F5 load balancers

**With third-party apps**:
- Linux (OpenSCEP, sscep)
- OpenWrt / embedded

---

### Does UCM work on Windows?

**Not directly**, but options:

1. **WSL2** (Windows Subsystem for Linux)
   ```powershell
   wsl --install
   # Then install UCM in WSL Ubuntu
   ```

2. **Docker Desktop** (recommended)
   ```powershell
   # Install Docker Desktop
   docker-compose up -d
   ```

3. **Linux VM** (VirtualBox, Hyper-V)

**Windows clients** can use UCM (via browser/API)

---

## 🆘 Support

### I found a bug, where to report it?

**GitHub Issues**: https://github.com/NeySlim/ultimate-ca-manager/issues

**Include**:
- UCM version (`ucm --version` or About page)
- OS and version
- Steps to reproduce
- Error logs
- Screenshots if relevant

---

### Where to ask for help?

1. **Documentation Wiki** (you are here!)
2. **[Troubleshooting](Troubleshooting)** - Common issues
3. **[GitHub Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)** - General questions
4. **[GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)** - Bugs

---

### Is UCM free?

**Yes!** UCM is open source under BSD-3-Clause license.

- ✅ Free use (personal, business)
- ✅ Modification allowed
- ✅ Distribution allowed
- ✅ No certificate limit
- ✅ Community support

**Commercial support**: Not yet available (v1.0.1)

---

**More questions?** → [GitHub Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)
