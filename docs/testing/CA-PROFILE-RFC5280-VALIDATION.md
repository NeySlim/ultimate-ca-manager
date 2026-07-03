# Validation — profil CA RFC 5280 (digest, KU, EKU)

## Contexte

Le wizard **Create CA** expose désormais :

- **Algorithme de signature** : Auto (aligné sur la clé), SHA-256, SHA-384, SHA-512
- **Profil certificat (RFC 5280)** : Key Usage + EKU (intermédiaire)

## Defaults (RFC 5280 §4.2.1.3 / pratique LE)

| Type | Courbe P-384 + Auto | Key Usage | EKU |
|------|---------------------|-----------|-----|
| Root | ecdsa-with-SHA384 | keyCertSign, cRLSign | — |
| Intermediate | ecdsa-with-SHA384 | digitalSignature, keyCertSign, cRLSign | serverAuth |

## Test lab

1. **Create CA** → Root → ECDSA P-384 → Signature **Auto** → Create
2. Export PEM → `openssl x509 -in ca.pem -noout -text | grep -E "Signature Algorithm|Key Usage|Extended"`

Attendu root :

```
Signature Algorithm: ecdsa-with-SHA384
Key Usage: Certificate Sign, CRL Sign
```

3. Créer une **Intermediate** sous cette root (P-384, Auto, serverAuth coché)

Attendu intermediate :

```
Signature Algorithm: ecdsa-with-SHA384
Key Usage: Digital Signature, Certificate Sign, CRL Sign
Extended Key Usage: TLS Web Server Authentication
```

## Tests automatisés

```bash
cd backend && python -m pytest tests/test_ca_profile.py tests/test_cas.py::TestCreateCA -q
```
