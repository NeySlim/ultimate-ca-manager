# WebAuthn / FIDO2 Support

**Version:** 1.8.2  
**Status:** ✅ Production Ready  
**Standard:** [W3C WebAuthn](https://www.w3.org/TR/webauthn/)

---

## Overview

UCM supports **passwordless authentication** using WebAuthn/FIDO2 security keys and biometrics. Login with YubiKey, Touch ID, Windows Hello, or fingerprint sensors.

### What is WebAuthn?

**Web Authentication API (WebAuthn)** enables strong, phishing-resistant authentication using:
- Hardware security keys (YubiKey, Titan Key, SoloKey)
- Biometric sensors (Touch ID, Windows Hello, fingerprint)
- Platform authenticators (built into devices)

---

## Features

### ✅ Passwordless Login
- No passwords to remember or steal
- Phishing-resistant (credential bound to domain)
- Works across devices

### 🔐 Multi-Factor Support
- Use as primary authentication
- Or combine with password (2FA)
- Multiple credentials per user

### 🔑 Supported Authenticators
- **USB Security Keys**: YubiKey, Titan, SoloKey
- **NFC Keys**: Tap-to-login on mobile
- **Biometrics**: Touch ID, Face ID, Windows Hello
- **Platform**: Built-in TPM authenticators

---

## Setup

### Enable WebAuthn

1. **Navigate to My Account**
   - Click your username → "My Account"
   - Go to "Security" tab

2. **Register Security Key**
   - Click "Add Security Key"
   - Insert key or prepare biometric
   - Follow browser prompts
   - Give it a friendly name (e.g., "YubiKey 5")

3. **Test Login**
   - Logout
   - On login page, click "Use Security Key"
   - Insert/touch key when prompted

---

## Registration Process

### Step 1: Initiate Registration

Click "Add Security Key" in My Account → Security.

### Step 2: Browser Prompt

Browser will ask to:
1. Insert security key (if USB)
2. Touch sensor to verify presence
3. Enter PIN (if key requires it)
4. Approve registration

### Step 3: Name Credential

Give it a memorable name:
- ✅ "YubiKey 5 - Office"
- ✅ "MacBook Touch ID"
- ✅ "Windows Hello"  
- ❌ "Key1" (not descriptive)

### Step 4: Credential Stored

Credential is now registered and ready to use!

---

## Login with WebAuthn

### Primary Authentication

1. **Go to UCM login page**
2. **Click "Use Security Key"** (no username needed)
3. **Insert/touch key**
4. **Logged in!**

### With Username (Identified Mode)

1. **Enter username**
2. **Click "Use Security Key"**
3. **Insert/touch your key**
4. **Logged in!**

### Fallback to Password

If key not available:
- Click "Use Password Instead"
- Enter traditional credentials

---

## Managing Credentials

### View Credentials

My Account → Security shows:
- Credential name (your label)
- Credential ID (unique identifier)
- Created date
- Last used date
- Total uses

### Remove Credential

1. Click "Remove" next to credential
2. Confirm deletion
3. Credential immediately revoked

**⚠️ Warning:** Removing all credentials requires password login!

### Multiple Credentials

Register multiple keys:
- Primary key (daily use)
- Backup key (stored securely)
- Biometric (convenience)
- Platform authenticator (device-specific)

---

## Supported Browsers

### ✅ Full Support
- **Chrome/Edge**: 67+ (Windows, macOS, Linux, Android)
- **Firefox**: 60+ (Windows, macOS, Linux)
- **Safari**: 13+ (macOS, iOS)
- **Opera**: 54+

### Platform-Specific

| Platform | USB Keys | Biometric | Platform Auth |
|----------|----------|-----------|---------------|
| Windows 10+ | ✅ | ✅ (Hello) | ✅ |
| macOS | ✅ | ✅ (Touch ID) | ✅ |
| Linux | ✅ | ⚠️ (limited) | ⚠️ |
| iOS 14+ | ⚠️ (NFC) | ✅ (Face/Touch ID) | ✅ |
| Android 7+ | ✅ (USB-C/NFC) | ✅ | ✅ |

---

## Security Keys

### YubiKey

**Models Supported:**
- YubiKey 5 Series (USB-A, USB-C, NFC)
- YubiKey 5C Nano
- YubiKey 5 NFC
- Security Key by Yubico

**Setup:**
1. Insert YubiKey
2. Register in UCM
3. Touch gold sensor when prompted

### Google Titan

**Models Supported:**
- Titan Security Key (USB-A/NFC)
- Titan Security Key USB-C

**Setup:**
Similar to YubiKey - insert and touch.

### SoloKey

Open-source FIDO2 key:
- Solo v2
- SoloPRO

### Windows Hello

Built-in biometric or PIN:
1. Setup Windows Hello in Windows Settings
2. Register in UCM
3. Use face/fingerprint/PIN to login

### Touch ID / Face ID

macOS/iOS biometric:
- MacBook with Touch Bar
- iPhone/iPad with Face ID or Touch ID
- Credential stored in device Secure Enclave

---

## Troubleshooting

### Registration Fails

**Check:**
1. **Browser support**
   ```
   - Update to latest browser version
   - Try Chrome/Firefox if Safari fails
   ```

2. **HTTPS required**
   ```
   - WebAuthn only works over HTTPS
   - Localhost exempt for testing
   ```

3. **Key compatibility**
   ```
   - Use FIDO2-certified key
   - Update key firmware if available
   ```

### Login Fails

**"No credentials found"**
```
- Wrong username entered
- Credential not registered for this user
- Try "unidentified" mode (no username)
```

**"Credential not recognized"**
```
- Key registered on different account
- Credential revoked
- Try password login
```

**Timeout**
```
- Insert key within 60 seconds
- Check USB connection
- Try different USB port
```

### Browser Issues

**Chrome:** "Allow this site to see your security key"
```
- Click "Allow" in permission prompt
- Check browser flags: chrome://flags/#enable-webauthn
```

**Firefox:** Permission denied
```
- about:config
- Set security.webauthn.enable = true
```

**Safari:** No prompt appears
```
- Check System Preferences → Security
- Ensure Touch ID enabled
```

---

## Security Best Practices

### ✅ Do

- **Register backup key** - Store securely offsite
- **Use PIN protection** - If key supports it
- **Name credentials clearly** - Know which is which
- **Revoke lost keys immediately**
- **Use biometric** - For convenience

### ❌ Don't

- **Share security keys** - Each user should have own
- **Leave key inserted** - Remove after use
- **Forget backup** - Have alternative login method
- **Trust public computers** - Use only on trusted devices

---

## Advanced Configuration

### Require WebAuthn

Force all users to use security keys:

System Settings → Authentication:
```
☑ Require WebAuthn for all users
☐ Allow password fallback
```

### Attestation

Verify key authenticity:
```
☑ Require attestation
☐ Allow self-attestation
☑ Verify against FIDO MDS
```

### User Verification

Require PIN/biometric:
```
User Verification: required | preferred | discouraged
```

---

## API Usage

See [API Reference](API-Reference) for programmatic WebAuthn operations.

---

## Related Documentation

- [User Management](User-Management) - Admin user configuration
- [Security](Security) - Best practices
- [Troubleshooting](Troubleshooting) - Common issues

---

## Standards Compliance

- ✅ **W3C WebAuthn Level 2**
- ✅ **FIDO2** (CTAP2)
- ✅ **FIDO U2F** (legacy, for compatibility)

---

**Need Help?** See [Troubleshooting](Troubleshooting) or [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
