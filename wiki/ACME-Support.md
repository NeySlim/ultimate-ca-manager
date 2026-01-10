# ACME Protocol Support

**Version:** 1.8.2  
**Status:** ✅ Production Ready  
**RFC:** [RFC 8555](https://datatracker.ietf.org/doc/html/rfc8555)

---

## Overview

UCM provides a **full ACME v2 server** implementation, making it compatible with all Let's Encrypt clients like certbot, acme.sh, and more. Run your own internal certificate authority with automated certificate issuance!

### What is ACME?

**Automatic Certificate Management Environment (ACME)** is a protocol for automating certificate issuance and renewal. It's the technology behind Let's Encrypt.

---

## Features

### ✅ Complete ACME v2 Implementation
- **Account Management** - Create, update, deactivate accounts
- **Order Processing** - Handle certificate requests
- **Challenge Validation** - HTTP-01 and DNS-01
- **Certificate Issuance** - Automated signing and delivery
- **Renewal Support** - Seamless certificate renewal

### 🔐 Challenge Types Supported

#### HTTP-01 Challenge
- Place a file at `http://domain/.well-known/acme-challenge/`
- Best for public-facing web servers
- Automatic validation

#### DNS-01 Challenge  
- Add a TXT record to DNS
- Works with wildcard certificates
- Supports multiple domains

---

## Configuration

### Enable ACME Server

1. **Navigate to System Settings**
   - Click "System Settings" in sidebar
   - Go to "ACME Configuration" tab

2. **Enable ACME**
   ```
   ☑ Enable ACME Server
   Directory URL: https://your-ucm:8443/acme/directory
   ```

3. **Configure Defaults**
   - Default CA for ACME certificates
   - Challenge timeout (default: 300s)
   - Rate limiting (optional)

### ACME Directory URL

```
https://your-ucm-server:8443/acme/directory
```

This is the URL you'll use with ACME clients.

---

## Usage with Certbot

### Initial Setup

```bash
# Install certbot
sudo apt install certbot  # Debian/Ubuntu
sudo dnf install certbot  # RHEL/Rocky/Alma

# Set your UCM ACME directory
export ACME_DIR="https://ucm.example.com:8443/acme/directory"
```

### HTTP-01 Challenge

```bash
# Request a certificate
sudo certbot certonly \
  --standalone \
  --server $ACME_DIR \
  --preferred-challenges http \
  -d example.com \
  -d www.example.com \
  --email admin@example.com \
  --agree-tos \
  --no-eff-email
```

### DNS-01 Challenge (Wildcard)

```bash
# For wildcard certificates
sudo certbot certonly \
  --manual \
  --server $ACME_DIR \
  --preferred-challenges dns \
  -d "*.example.com" \
  -d example.com \
  --email admin@example.com \
  --agree-tos
```

### Auto-Renewal

```bash
# Test renewal
sudo certbot renew --dry-run --server $ACME_DIR

# Setup cron for auto-renewal
sudo crontab -e
# Add: 0 2 * * * /usr/bin/certbot renew --quiet --server https://ucm.example.com:8443/acme/directory
```

---

## Usage with acme.sh

### Installation

```bash
curl https://get.acme.sh | sh
source ~/.bashrc
```

### Request Certificate

```bash
# Set ACME server
export ACME_SERVER="https://ucm.example.com:8443/acme/directory"

# HTTP-01 validation
acme.sh --issue \
  --server $ACME_SERVER \
  -d example.com \
  -w /var/www/html

# DNS-01 validation (example with Cloudflare)
export CF_Token="your-cloudflare-token"
export CF_Account_ID="your-account-id"

acme.sh --issue \
  --server $ACME_SERVER \
  --dns dns_cf \
  -d example.com \
  -d "*.example.com"
```

### Auto-Renewal

```bash
# acme.sh sets up auto-renewal automatically
# Check with:
acme.sh --cron --server $ACME_SERVER
```

---

## Account Management

### View ACME Accounts

Navigate to: **ACME Accounts** page in UCM

Shows:
- Account ID
- Email address
- Status (active/deactivated)
- Created date
- Number of certificates

### Deactivate Account

```bash
# With certbot
certbot unregister --server $ACME_DIR

# Account remains in UCM but is marked inactive
```

---

## Certificate Orders

### View Orders

**ACME Orders** page shows:
- Order ID
- Domain(s) requested
- Status (pending, processing, valid, invalid)
- Challenges (pending, valid, invalid)
- Created/expires dates

### Order Lifecycle

```
1. New Order     → Client requests certificate
2. Pending       → Awaiting challenge validation
3. Processing    → UCM validates challenges
4. Valid         → Certificate issued
5. (or Invalid)  → Challenge failed
```

---

## Troubleshooting

### Certificate Request Failed

**Check order status in UCM:**
- Go to ACME Orders
- Find your order
- Check challenge status

**Common issues:**

1. **HTTP-01 challenge fails**
   ```
   - Ensure port 80 is accessible
   - Check firewall rules
   - Verify domain points to your server
   ```

2. **DNS-01 challenge fails**
   ```
   - Verify TXT record was created
   - Wait for DNS propagation (up to 5 minutes)
   - Check DNS with: dig _acme-challenge.example.com TXT
   ```

3. **Rate limiting**
   ```
   - UCM may have rate limits configured
   - Check System Settings → ACME
   - Contact admin to adjust limits
   ```

### Debug Mode

```bash
# Certbot verbose mode
sudo certbot certonly --server $ACME_DIR --verbose

# acme.sh debug mode
acme.sh --issue --server $ACME_SERVER -d example.com --debug 2
```

---

## Security Considerations

### HTTPS Required

- ACME server MUST use HTTPS
- Self-signed UCM certificates may need CA import:

```bash
# Import UCM CA certificate
sudo cp ucm-ca.pem /usr/local/share/ca-certificates/ucm-ca.crt
sudo update-ca-certificates

# Or with certbot --no-verify-ssl (NOT recommended for production)
```

### Account Authentication

- ACME accounts are authenticated via key pairs
- Private keys stored client-side
- UCM stores public keys only

### Challenge Security

- HTTP-01: Validates domain ownership via web server
- DNS-01: Validates domain ownership via DNS
- Both prevent unauthorized certificate issuance

---

## API Endpoints

### ACME Directory

```
GET /acme/directory
```

Returns ACME directory with endpoints for:
- newAccount
- newOrder  
- newNonce
- revokeCert

### Example Response

```json
{
  "newAccount": "https://ucm.example.com:8443/acme/new-account",
  "newOrder": "https://ucm.example.com:8443/acme/new-order",
  "newNonce": "https://ucm.example.com:8443/acme/new-nonce",
  "revokeCert": "https://ucm.example.com:8443/acme/revoke-cert"
}
```

---

## Use Cases

### Internal Services

```bash
# Automated certificates for internal services
acme.sh --issue --server $ACME_SERVER \
  -d gitlab.internal.example.com \
  -d jenkins.internal.example.com
```

### Development Environments

```bash
# Quick certificates for dev/staging
certbot certonly --server $ACME_DIR \
  -d dev.example.com --standalone
```

### Wildcard Certificates

```bash
# Cover all subdomains
certbot certonly --server $ACME_DIR \
  --manual --preferred-challenges dns \
  -d "*.example.com"
```

---

## Related Documentation

- [Certificate Operations](Certificate-Operations) - Manual certificate management
- [CA Management](CA-Management) - Configure CAs for ACME
- [API Reference](API-Reference) - ACME API details
- [Troubleshooting](Troubleshooting) - Common issues

---

## Standards Compliance

- ✅ **RFC 8555** - ACME Protocol
- ✅ **RFC 8738** - ACME IP Identifier Validation
- ✅ **HTTP-01** - Web-based validation
- ✅ **DNS-01** - DNS-based validation

---

**Need Help?** See [Troubleshooting](Troubleshooting) or [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
