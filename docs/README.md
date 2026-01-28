# UCM Documentation

Ce dossier contient la documentation technique du projet Ultimate CA Manager.

## Documents Disponibles

### Spécifications API

1. **[API_REFERENCE.md](./API_REFERENCE.md)**
   - Documentation complète des 155+ endpoints API v2
   - Exemples de requêtes et réponses
   - Authentification et sécurité

2. **[UCM-API-SPECIFICATION.md](./UCM-API-SPECIFICATION.md)**
   - Spécification du contrat API v2
   - Structures de réponse standardisées

3. **[API-WIRING-AUDIT.md](./API-WIRING-AUDIT.md)**
   - Historique de l'audit frontend ↔ backend
   - Corrections appliquées

## Statut Actuel

**Date:** 2026-01-28  
**Statut:** ✅ PRODUCTION READY

### Fonctionnalités Complètes

#### PKI Core
- ✅ Gestion complète des CAs (création, import, export, delete)
- ✅ Gestion des certificats (génération, signature, révocation, renouvellement)
- ✅ CSRs (upload, signature, export)
- ✅ Templates de certificats
- ✅ CRL & OCSP
- ✅ SCEP & ACME

#### Import/Export
- ✅ Import fichier (PEM, DER, PKCS12, PKCS7)
- ✅ Coller PEM/JSON directement
- ✅ Auto-détection du format
- ✅ Auto-routage (CA vs certificat)
- ✅ Détection des doublons avec mise à jour
- ✅ Export PEM/DER/PKCS12
- ✅ Copier PEM en un clic

#### Authentification
- ✅ Login username/password
- ✅ 2FA TOTP (Google Authenticator)
- ✅ WebAuthn/FIDO2 (YubiKey)
- ✅ mTLS (certificat client)
- ✅ Cascade automatique des méthodes

#### UI/UX
- ✅ 6 thèmes avec gradients
- ✅ Layout split-view cohérent
- ✅ TreeView pour hiérarchie CAs
- ✅ Audit logs avec filtres et export

## Architecture

### Backend
- **Framework:** Flask + SQLAlchemy
- **API Version:** v2
- **Base URL:** `/api/v2`
- **Auth:** Session-based (cookie)
- **Database:** SQLite (`/opt/ucm/data/ucm.db`)

### Frontend
- **Framework:** React 18
- **Router:** React Router v6
- **UI:** Radix UI + TailwindCSS
- **Build:** Vite
- **Deployment:** `/opt/ucm/frontend/static/`

### Conventions API

**Réponse Standard (Lists):**
```json
{
  "data": [...],
  "meta": {
    "total": 100,
    "page": 1,
    "per_page": 20,
    "total_pages": 5
  }
}
```

**Réponse Standard (Single/Config):**
```json
{
  "data": {...}
}
```

**Mutations:**
```json
{
  "success": true,
  "data": {...},
  "message": "Operation successful"
}
```

## Build & Deploy

```bash
# Frontend build
cd /root/ucm-src/frontend
npm run build

# Deploy
cp dist/assets/* /opt/ucm/frontend/static/assets/
cp dist/index.html /opt/ucm/frontend/templates/index.html
sudo systemctl restart ucm
```

## Ressources

- **Production:** https://netsuit.lan.pew.pet:8443
- **Source:** `/root/ucm-src` (branch: `redesign/v3.0.0-clean`)
- **Database:** `/opt/ucm/data/ucm.db`
- **Logs:** `/var/log/ucm/`
