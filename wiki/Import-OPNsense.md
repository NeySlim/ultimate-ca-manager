# Import from OPNsense

**Version:** 1.8.2

## Overview

UCM can import certificates and CAs directly from OPNsense firewalls.

## Prerequisites

- OPNsense API key and secret
- Network access to OPNsense (typically port 443)
- Admin permissions in UCM

## Configuration

1. **Get OPNsense API Credentials**
   - Login to OPNsense
   - System → Access → Users
   - Edit your user → API Keys
   - Generate new key
   - Save key and secret

2. **Configure in UCM**
   - System Settings → Integrations
   - OPNsense Import tab
   - Enter:
     - Host: https://opnsense.example.com
     - API Key: your-key
     - API Secret: your-secret

3. **Test Connection**
   - Click "Test Connection"
   - Should show: ✅ Connected to OPNsense

## Import Process

1. **Navigate to Import**
   - Tools → Import from OPNsense

2. **Select Items**
   - ☑ Root CAs
   - ☑ Intermediate CAs
   - ☑ Certificates
   - ☑ Include private keys (if available)

3. **Import**
   - Click "Start Import"
   - Progress shown for each item
   - Summary displayed

## What Gets Imported

- Certificate Authorities (Root, Intermediate)
- Server certificates
- Client certificates
- Private keys (if exported from OPNsense)
- Certificate chains

## Limitations

- OPNsense must have export enabled
- Some data may not be preserved (custom extensions)
- Requires manual configuration of OCSP/CRL URLs

See [Troubleshooting](Troubleshooting) for import issues.
