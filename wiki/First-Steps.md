# First Steps - UCM v1.8.2

Getting started with Ultimate CA Manager after installation.

---

## 🎯 Initial Configuration

### 1. First Login

Access the web interface at: `https://your-server:8443`

**Default Credentials:**
- Username: `admin`
- Password: `changeme123`

⚠️ **You will be forced to change the password on first login for security.**

---

### 2. Change Admin Password

After logging in for the first time:

1. You'll be prompted to change your password
2. Enter a strong password (minimum 12 characters recommended)
3. Confirm the new password
4. Click "Change Password"

---

### 3. Configure Basic Settings

Navigate to **Settings** → **System Configuration**

#### HTTPS Certificate
- By default, UCM uses a self-signed certificate
- Upload your own certificate for production use
- Or configure Let's Encrypt/ACME for automatic certificates

#### SMTP Configuration (Email Notifications)
- Configure SMTP server for certificate expiry notifications
- Test email delivery
- Set notification thresholds

#### Server FQDN
- Set your server's fully qualified domain name
- Used for SCEP, OCSP, and CRL URLs
- Example: `ucm.example.com`

---

### 4. Create Your First Certificate Authority

Navigate to **Certificate Authorities** → **Create CA**

**Basic Options:**
- **CA Name**: Internal Root CA
- **Key Type**: RSA 4096 or EC P-384
- **Validity**: 10 years (3650 days) for root CA
- **Subject DN**:
  - CN: Internal Root CA
  - O: Your Organization
  - C: US

**Advanced Options:**
- Enable CRL Distribution
- Enable OCSP
- Set key usage constraints

Click **Create CA** to generate your root certificate authority.

---

### 5. Issue Your First Certificate

Navigate to **Certificates** → **Create Certificate**

**Certificate Details:**
- **Common Name**: server.example.com
- **Subject Alternative Names**: DNS:server.example.com
- **Key Type**: RSA 2048 or EC P-256
- **Validity**: 1 year (365 days)

**Usage:**
- Select appropriate key usage (Server Authentication, Client Authentication, etc.)
- Add any extended key usages needed

Click **Issue Certificate** to create the certificate.

---

### 6. Download and Use Your Certificate

After issuance:

1. **Download formats:**
   - PEM (certificate + key)
   - PKCS#12 (.p12/.pfx) with password
   - Certificate only
   - Chain + Certificate

2. **Install on your server:**
   ```bash
   # Example for Nginx
   ssl_certificate /etc/ssl/certs/server.crt;
   ssl_certificate_key /etc/ssl/private/server.key;
   ```

---

## 📚 Next Steps

### Enable Protocol Services

- **[SCEP Server](SCEP-Server)** - Automated certificate enrollment
- **[OCSP Responder](OCSP-Responder)** - Real-time certificate status
- **[CRL Distribution](CRL-CDP)** - Certificate revocation lists
- **[ACME Server](ACME-Support)** - Let's Encrypt-compatible protocol

### Advanced Features

- **[mTLS Authentication](MTLS-Authentication)** - Client certificate login
- **[WebAuthn/FIDO2](WebAuthn-Support)** - Hardware key authentication
- **[User Management](User-Management)** - Create additional users
- **[Backup & Restore](Backup-Restore)** - Protect your CA data

### User Interface

- **[Theme Customization](Themes)** - Choose from 8 themes
- **[Dashboard Overview](Dashboard)** - Monitor your PKI

---

## 🔐 Security Best Practices

1. **Offline Root CA**: Consider keeping root CA offline in production
2. **Strong Passwords**: Use unique, complex passwords
3. **Regular Backups**: Backup CA data and database regularly
4. **Certificate Revocation**: Monitor and revoke compromised certificates
5. **Access Control**: Use role-based access control (RBAC)
6. **mTLS**: Enable mutual TLS for enhanced security
7. **2FA/WebAuthn**: Use hardware keys for admin accounts

---

## 📊 Quick Reference

| Task | Location |
|------|----------|
| Create CA | Certificate Authorities → Create CA |
| Issue Certificate | Certificates → Create Certificate |
| Revoke Certificate | Certificates → [Certificate] → Revoke |
| View CRL | CRL Information (public page) |
| SCEP URL | Settings → SCEP Configuration |
| OCSP URL | Settings → OCSP Configuration |
| Change Password | Settings → My Account |
| Add User | Settings → User Management |
| System Logs | Settings → System Logs |

---

## 🐛 Common Issues

### Can't Access Web Interface

```bash
# Check if service is running
sudo systemctl status ucm

# Check firewall
sudo ufw status

# View logs
sudo journalctl -u ucm -n 50
```

### Certificate Won't Download

- Clear browser cache
- Try different export format
- Check certificate is issued (not pending/revoked)

### SCEP Not Working

- Verify SCEP is enabled in settings
- Check SCEP URL is accessible
- Review SCEP server logs

---

## 💡 Tips & Tricks

- Use **keyboard shortcuts** for quick navigation
- **Favorite CAs** for quick access
- Use **filters** to find certificates quickly
- Set up **email notifications** for expiring certificates
- Use **certificate templates** for common certificate types
- Export certificates in **bulk** using API

---

**Need Help?** Check [Troubleshooting](Troubleshooting) or [FAQ](FAQ)

**Last Updated**: 2026-01-09  
**Version**: 1.8.3-beta
