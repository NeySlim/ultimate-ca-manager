# Certificate Export

**Version:** 1.8.2

## Export Formats

UCM supports multiple export formats with JWT authentication (v1.8.2+).

### PEM Format

**Simple:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://ucm.example.com/api/v1/certificates/123/export?format=pem
```

**With Private Key:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://ucm.example.com/api/v1/certificates/123/export?format=pem&include_key=true
```

**With Chain:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://ucm.example.com/api/v1/certificates/123/export?format=pem&chain=true
```

**Full Chain:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://ucm.example.com/api/v1/certificates/123/export?format=pem&chain=true&include_key=true
```

### DER Format

```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://ucm.example.com/api/v1/certificates/123/export?format=der
```

### PKCS#12 (.p12/.pfx)

Password-protected archive with certificate + key:

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"password": "your-password"}' \
  https://ucm.example.com/api/v1/certificates/123/export/pkcs12
```

## Web UI Export

All formats available via UI:
1. Navigate to certificate details
2. Click "Export" dropdown
3. Select format
4. For PKCS#12: Enter password in modal
5. Download automatically starts

See [Certificate-Operations](Certificate-Operations) for more.
