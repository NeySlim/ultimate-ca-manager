# SCEP Server

**Version:** 1.8.2  
**Status:** ✅ Production Ready  
**RFC:** [RFC 8894](https://datatracker.ietf.org/doc/html/rfc8894)

---

## Overview

**Simple Certificate Enrollment Protocol (SCEP)** enables automated certificate enrollment for network devices, mobile devices, and IoT equipment. UCM provides a full SCEP server for enterprise device management.

### What is SCEP?

SCEP automates certificate distribution to devices that can't use interactive enrollment methods. Common uses include:
- Mobile Device Management (MDM)
- Network equipment (routers, switches, firewalls)
- IoT devices
- VPN clients

---

## Features

### ✅ Full SCEP Implementation
- **GetCACert** - Retrieve CA certificate
- **GetCACaps** - Query server capabilities
- **PKIOperation** - Certificate enrollment
- **Auto-Approval** - Optional automated enrollment
- **Manual Approval** - Admin review before issuance

### 🔐 Supported Operations
- Initial enrollment (new devices)
- Certificate renewal
- Certificate revocation
- Challenge-based authentication

---

## Configuration

### Enable SCEP Server

1. **Navigate to System Settings**
   - Go to "SCEP Configuration" tab

2. **Enable SCEP**
   ```
   ☑ Enable SCEP Server
   SCEP URL: https://your-ucm:8443/scep
   ```

3. **Configure Options**
   - **Auto-Approval**: Enable for trusted networks
   - **Challenge Password**: Static shared secret (optional)
   - **Default CA**: Select CA for device certificates
   - **Certificate Validity**: Default 365 days

---

## SCEP Endpoints

### Base URL

```
https://your-ucm-server:8443/scep
```

### Operations

- `GET /scep?operation=GetCACert` - Download CA certificate
- `GET /scep?operation=GetCACaps` - Query capabilities  
- `POST /scep?operation=PKIOperation` - Enroll certificate

---

## iOS/macOS Enrollment

### Configuration Profile

Create a `.mobileconfig` file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <array>
        <dict>
            <key>PayloadType</key>
            <string>com.apple.security.scep</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
            <key>PayloadIdentifier</key>
            <string>com.example.scep</string>
            <key>PayloadUUID</key>
            <string>UNIQUE-UUID-HERE</string>
            <key>PayloadDisplayName</key>
            <string>Device Certificate</string>
            <key>PayloadDescription</key>
            <string>Automatically enrolls device certificate</string>
            <key>URL</key>
            <string>https://ucm.example.com:8443/scep</string>
            <key>Subject</key>
            <array>
                <array>
                    <array>
                        <string>CN</string>
                        <string>Device Name</string>
                    </array>
                </array>
            </array>
            <key>Challenge</key>
            <string>your-challenge-password</string>
            <key>Keysize</key>
            <integer>2048</integer>
            <key>Key Type</key>
            <string>RSA</string>
            <key>Key Usage</key>
            <integer>5</integer>
        </dict>
    </array>
    <key>PayloadDisplayName</key>
    <string>UCM Device Enrollment</string>
    <key>PayloadIdentifier</key>
    <string>com.example.scep.profile</string>
    <key>PayloadUUID</key>
    <string>UNIQUE-PROFILE-UUID</string>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
</dict>
</plist>
```

### Deployment

1. Email profile to users
2. Use MDM to push profile
3. Host on web server for download
4. Users install via Settings → Profile

---

## Android Enrollment

### Using Native Certificate Installer

1. **Download CA Certificate**
   ```
   curl -o ca.pem https://ucm.example.com:8443/scep?operation=GetCACert
   ```

2. **Install CA**
   - Settings → Security → Install from storage
   - Select ca.pem

3. **Request Certificate via SCEP Client**
   - Use third-party SCEP client app
   - Enter SCEP URL
   - Provide challenge password

---

## Windows Enrollment

### Using certreq

1. **Create Request File** (`request.inf`)

```ini
[Version]
Signature="$Windows NT$"

[NewRequest]
Subject = "CN=Computer01,O=Example Corp"
KeyLength = 2048
Exportable = TRUE
MachineKeySet = TRUE
SMIME = FALSE
PrivateKeyArchive = FALSE
UserProtected = FALSE
UseExistingKeySet = FALSE
ProviderName = "Microsoft RSA SChannel Cryptographic Provider"
ProviderType = 12
RequestType = PKCS10
KeyUsage = 0xA0

[EnhancedKeyUsageExtension]
OID=1.3.6.1.5.5.7.3.1 ; Server Authentication
OID=1.3.6.1.5.5.7.3.2 ; Client Authentication
```

2. **Enroll via SCEP**

```powershell
# Create CSR
certreq -new request.inf request.csr

# Submit to SCEP (requires SCEP client)
# Use third-party tool like Klondike SCEP Client
```

---

## Linux Enrollment

### Using sscep

```bash
# Install sscep
sudo apt install sscep  # Debian/Ubuntu
sudo dnf install sscep  # RHEL/Rocky

# Get CA certificate
sscep getca \
  -u https://ucm.example.com:8443/scep \
  -c ca.pem

# Generate key and request
openssl genrsa -out device.key 2048
openssl req -new -key device.key -out device.csr \
  -subj "/CN=device01.example.com"

# Enroll
sscep enroll \
  -u https://ucm.example.com:8443/scep \
  -c ca.pem \
  -k device.key \
  -r device.csr \
  -l device.pem \
  -E device.cer \
  -C your-challenge-password
```

---

## SCEP Request Management

### View Pending Requests

Navigate to: **SCEP Requests** page

Shows:
- Request ID
- Device identifier (CN from CSR)
- Request date
- Status (pending, approved, rejected)
- Fingerprint

### Approve Request

1. Click request in list
2. Review CSR details:
   - Subject DN
   - Public key
   - Extensions
3. Click "Approve" or "Reject"

### Auto-Approval Rules

Configure in System Settings → SCEP:

```
☑ Auto-approve requests from:
  - Known IP ranges: 10.0.0.0/8, 192.168.0.0/16
  - Valid challenge password
  - Subject matches pattern: CN=*.example.com
```

---

## Challenge Password

### Static Challenge

Set in SCEP Configuration:
```
Challenge Password: MySecretPassword123
```

All devices use same password (simple but less secure).

### Dynamic Challenge

Generate unique passwords per device:

1. Create challenge in UCM
2. Assign to device/user
3. Use once for enrollment
4. Password expires after use

---

## Certificate Templates

### Default Template

SCEP certificates issued with:
- **Validity**: 365 days (configurable)
- **Key Usage**: Digital Signature, Key Encipherment
- **Extended Key Usage**: Client Authentication
- **Subject**: From CSR

### Custom Templates

Configure per-device-type templates:

**Mobile Devices**
```
Validity: 730 days
EKU: Client Auth, Email Protection
```

**Network Equipment**
```
Validity: 1095 days
EKU: Client Auth, Server Auth
```

---

## Monitoring

### SCEP Statistics

Dashboard shows:
- Total enrollments (last 30 days)
- Pending requests
- Auto-approved vs manual
- Rejected requests
- Success rate

### Logs

View SCEP activity:
- Enrollment requests
- Approvals/rejections
- Challenge validation failures
- Certificate issuance

---

## Troubleshooting

### Enrollment Fails

**Check UCM logs:**
```bash
sudo journalctl -u ucm -f | grep SCEP
```

**Common issues:**

1. **Invalid challenge password**
   ```
   - Verify password in device config
   - Check UCM SCEP settings
   - Ensure no typos/encoding issues
   ```

2. **CA certificate not trusted**
   ```
   - Install UCM CA on device first
   - Use GetCACert operation
   - Verify certificate chain
   ```

3. **Request pending forever**
   ```
   - Auto-approval may be disabled
   - Check SCEP Requests page in UCM
   - Manually approve if needed
   ```

### iOS Profile Installation Fails

```
- Profile must be signed or device supervised
- SCEP URL must use HTTPS
- CA certificate must be trusted
- Check device logs in Console.app
```

### Android Enrollment Issues

```
- Some devices don't support SCEP natively
- Use third-party SCEP client from Play Store
- Verify CA is installed in system trust store
```

---

## Security Best Practices

### Challenge Passwords

- ✅ Use dynamic/one-time passwords
- ✅ Rotate static passwords regularly  
- ❌ Don't hardcode in profiles
- ❌ Don't use weak passwords

### Network Security

- ✅ Use HTTPS only (no HTTP)
- ✅ Restrict SCEP endpoint to internal network
- ✅ Use firewall rules for IP filtering
- ✅ Enable auto-approval only for trusted subnets

### Certificate Policies

- ✅ Short validity periods (1 year max)
- ✅ Automatic renewal before expiration
- ✅ Revoke certificates for lost devices
- ✅ Monitor enrollment activity

---

## Integration Examples

### MDM Systems

**Jamf Pro (macOS/iOS)**
```
- Create configuration profile with SCEP payload
- Deploy via Jamf policies
- Use Jamf variables for subject
```

**Microsoft Intune (Windows/Android/iOS)**
```
- Add SCEP certificate profile
- Assign to device groups
- Monitor deployment status
```

### Network Equipment

**Cisco IOS**
```ios
crypto pki trustpoint UCM
 enrollment url https://ucm.example.com:8443/scep
 revocation-check none
 
crypto pki authenticate UCM
crypto pki enroll UCM
```

**Fortinet FortiGate**
```
config vpn certificate local
  edit "device-cert"
    set scep-url "https://ucm.example.com:8443/scep"
    set scep-password "challenge-password"
  next
end
```

---

## API Reference

See [API Reference](API-Reference) for programmatic SCEP operations.

---

## Related Documentation

- [Certificate Operations](Certificate-Operations) - Manual certificate issuance
- [CA Management](CA-Management) - Configure CAs for SCEP
- [User Management](User-Management) - Admin approval workflow
- [Troubleshooting](Troubleshooting) - Common issues

---

## Standards Compliance

- ✅ **RFC 8894** - Simple Certificate Enrollment Protocol (SCEP)
- ✅ **PKCS#7** - Cryptographic Message Syntax
- ✅ **PKCS#10** - Certificate Request Syntax

---

**Need Help?** See [Troubleshooting](Troubleshooting) or [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
