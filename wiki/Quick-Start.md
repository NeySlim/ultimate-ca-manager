# 🚀 Quick Start - UCM

Quick start guide to get operational in 10 minutes.

---

## ⏱️ Quick Installation (5 minutes)

### Option 1: Debian/Ubuntu (Recommended)

```bash
# Download DEB package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.6.0/ucm_1.6.0_all.deb

# Install
sudo dpkg -i ucm_1.6.0_all.deb

# Service starts automatically
sudo systemctl status ucm
```

**Access**: https://localhost:8443

### Option 2: RHEL/CentOS/Fedora

```bash
# Download RPM package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.6.0/ucm-1.6.0-1.noarch.rpm

# Install
sudo rpm -ivh ucm-1.6.0-1.noarch.rpm

# Service starts automatically
sudo systemctl status ucm
```

**Access**: https://localhost:8443

### Option 3: Manual Installation

```bash
# Clone repository
git clone -b v1.6.0 https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager

# Run installer
sudo ./scripts/install/install.sh

# Start UCM
sudo systemctl start ucm
```

**Access**: https://localhost:8443

---

## 🔐 First Login (2 minutes)

1. **Open browser**
   ```
   https://localhost:8443
   ```

2. **Accept self-signed certificate**
   - Click "Advanced" or "Avancé"
   - Then "Continue to site" or "Proceed"

3. **Login**
   ```
   Username: admin
   Password: changeme123
   ```

4. **⚠️ Change password**
   - User menu (top right) → Profile
   - Security → Change Password
   - New password: min 8 characters

---

## 🏛️ Create Your PKI (3 minutes)

### Step 1: Create a Root CA

```
Menu → Certificate Authorities → Create New CA

Configuration:
├─ CA Type: Root CA
├─ Key Type: RSA 4096 bits
├─ Hash: SHA-384
├─ Validity: 7300 days (20 years)
└─ Common Name: My Company Root CA

Click "Create CA"
```

### Step 2: Create an Intermediate CA

```
Create New CA

Configuration:
├─ CA Type: Intermediate CA
├─ Parent CA: My Company Root CA
├─ Key Type: RSA 4096 bits
├─ Hash: SHA-256
├─ Validity: 3650 days (10 years)
└─ Common Name: My Company Issuing CA

Click "Create CA"
```

✅ **Your PKI is ready!**

---

## 📜 Issue Your First Certificate

### Server Certificate

```
Menu → Certificates → Issue New Certificate

Configuration:
├─ Issuing CA: My Company Issuing CA
├─ Certificate Type: Server Certificate
├─ Common Name: www.example.com
├─ Organization: My Company Inc.
├─ Key Type: RSA 2048
├─ Validity: 365 days
│
└─ Subject Alternative Names (SANs):
   ├─ www.example.com
   └─ example.com

Click "Issue Certificate"
```

### Download Certificate

```
1. Certificate appears in list
2. Click Actions → Export
3. Format: PKCS#12 (.pfx)
4. Password: ******** (choose strong password)
5. Download
```

✅ **You have your first certificate!**

---

## 🔄 Configure SCEP (Optional)

For automatic enrollment (iOS, Android, etc.)

```
Menu → SCEP → New Endpoint

Configuration:
├─ Endpoint Name: Mobile Devices
├─ Issuing CA: My Company Issuing CA
├─ Challenge Password: ****************
├─ Certificate Type: Client Certificate
├─ Validity: 365 days
└─ Auto-renewal: ✅ Enabled

Click "Create Endpoint"
```

**Generated SCEP URL**:
```
https://<your-server>:8443/scep/mobile-devices
```

---

## 📊 Check Dashboard

Return to Dashboard to see:

- ✅ Number of CAs created
- ✅ Certificates issued
- ✅ Active SCEP endpoints
- ✅ Activity charts

---

## 🎯 Next Steps

Now that your PKI is operational:

1. **[Read User Manual](User-Manual)** - Complete documentation
2. **[Configure CRL/OCSP](System-Configuration)** - Certificate revocation
3. **[Create users](User-Management)** - Delegate tasks
4. **[Configure backups](System-Configuration#backup)** - Secure your data
5. **[Deploy to production](Installation-Guide#production-deployment)** - Best practices

---

## 🆘 Need Help?

- **[Troubleshooting](Troubleshooting)** - Common problems
- **[FAQ](FAQ)** - Frequently asked questions
- **[GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)** - Community support

---

## ✅ Quick Start Checklist

- [ ] UCM installed and accessible
- [ ] Admin password changed
- [ ] Root CA created
- [ ] Intermediate CA created
- [ ] First certificate issued
- [ ] Certificate downloaded and tested
- [ ] SCEP configured (if needed)
- [ ] Dashboard verified

**Congratulations! You're ready to use UCM! 🎉**

---

**Total time**: ~10 minutes  
**Level**: Beginner  
**Prerequisites**: None

[← Back to Home](Home) | [User Manual →](User-Manual)
