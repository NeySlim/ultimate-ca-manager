# UCM API v2.0 - Documentation Complète

## 📚 Vue d'ensemble

L'API UCM v2.0 fournit 121 endpoints RESTful pour gérer l'ensemble du système de gestion de certificats.

## 🔗 Accès à la documentation

### Swagger UI (Interface Interactive)
- **URL**: `https://your-server:8443/api/docs`
- **Description**: Interface web interactive pour explorer et tester tous les endpoints
- **Authentification**: Cliquez sur "Authorize" et entrez votre token JWT

### Documentation Markdown
- **Fichier**: `/root/ucm-src/API_v2_COMPLETE.md`
- **Contenu**: Liste complète des 121 endpoints avec exemples

## 🏗️ Architecture API

### Base URL
```
https://your-server:8443/api/v2
```

### Authentification
Tous les endpoints requièrent un token JWT Bearer:
```bash
Authorization: Bearer <your-jwt-token>
```

### Obtention du token
```bash
POST /api/v2/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "your-password"
}
```

## 📋 Modules disponibles (15)

| Module | Endpoints | Description |
|--------|-----------|-------------|
| **auth** | 8 | Authentification, login, logout, tokens |
| **users** | 6 | Gestion des utilisateurs |
| **cas** | 10 | Gestion des CAs (Autorités de Certification) |
| **certificates** | 15 | Gestion des certificats |
| **csr** | 6 | Gestion des CSR (Certificate Signing Requests) |
| **templates** | 6 | Modèles de certificats |
| **profiles** | 6 | Profils de certificats |
| **acme** | 8 | Serveur ACME interne |
| **letsencrypt** | 5 | Proxy Let's Encrypt |
| **automated** | 7 | Renouvellements automatiques |
| **activity** | 3 | Logs d'activité |
| **dashboard** | 4 | Statistiques et vue d'ensemble |
| **export** | 4 | Export de certificats (PEM, PKCS12, etc.) |
| **settings** | 3 | Configuration système |
| **system** | 30 | Santé, monitoring, backups |

**Total**: **121 endpoints**

## 🚀 Exemples d'utilisation

### 1. Créer une nouvelle CA
```bash
curl -X POST https://localhost:8443/api/v2/cas \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "common_name": "My Root CA",
    "key_size": 4096,
    "validity_days": 3650,
    "ca_type": "root"
  }'
```

### 2. Lister les certificats
```bash
# Liste par défaut (triée par CN alphabétiquement)
curl -X GET "https://localhost:8443/api/v2/certificates" \
  -H "Authorization: Bearer $TOKEN"

# Filtrer par statut: valid, expired, expiring, revoked
curl -X GET "https://localhost:8443/api/v2/certificates?status=valid" \
  -H "Authorization: Bearer $TOKEN"

# Tri personnalisé (sort_by: subject, valid_to, created_at)
curl -X GET "https://localhost:8443/api/v2/certificates?sort_by=valid_to&sort_order=asc" \
  -H "Authorization: Bearer $TOKEN"
```

### 3. Renouveler un certificat
```bash
# Renouvelle le certificat en place (même ID, nouvelle clé)
curl -X POST "https://localhost:8443/api/v2/certificates/15/renew" \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Obtenir les statistiques
```bash
curl -X GET https://localhost:8443/api/v2/dashboard/stats \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Configurer ACME
```bash
curl -X PATCH https://localhost:8443/api/v2/acme/settings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "issuing_ca_id": 1
  }'
```

## 📊 Codes de réponse HTTP

| Code | Signification |
|------|---------------|
| 200 | Succès |
| 201 | Créé avec succès |
| 204 | Succès sans contenu |
| 400 | Requête invalide |
| 401 | Non authentifié |
| 403 | Non autorisé |
| 404 | Ressource non trouvée |
| 409 | Conflit (ressource déjà existante) |
| 422 | Erreur de validation |
| 500 | Erreur serveur |

## 🔐 Sécurité

### HTTPS obligatoire
- Tous les appels doivent utiliser HTTPS
- Certificat auto-signé accepté en développement avec `-k`

### Token JWT
- Durée de vie: 24 heures (configurable)
- Refresh possible via `/api/v2/auth/refresh`
- Logout invalide le token: `/api/v2/auth/logout`

### CSRF Protection (v2.0.0)
- Token CSRF retourné sur login/verify
- Header requis: `X-CSRF-Token` pour POST/PUT/DELETE/PATCH
- Stocké dans sessionStorage côté client

### Password Policy (v2.0.0)
- Minimum 8 caractères
- Requiert: majuscule, minuscule, chiffre, caractère spécial
- Blacklist de mots de passe courants
- API: `GET /api/v2/users/password-policy`

### Rate Limiting (v2.0.0)
- Auth endpoints: 10 req/min
- Heavy operations: 30 req/min
- Standard endpoints: 120 req/min
- Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`

### Private Key Encryption (v2.0.0)
- Chiffrement Fernet (AES-256-CBC + HMAC-SHA256)
- Variable: `KEY_ENCRYPTION_KEY` dans `/etc/ucm/ucm.env`
- Migration: `POST /api/v2/system/security/encrypt-all-keys`

### Permissions
- Contrôle d'accès basé sur les rôles utilisateurs
- Certains endpoints nécessitent des permissions admin

## 🆕 Nouveaux Endpoints Sécurité (v2.0.0)

### Audit Log Retention
```bash
# Obtenir config/stats retention
GET /api/v2/system/audit/retention

# Modifier retention (jours)
PUT /api/v2/system/audit/retention
{"retention_days": 90, "auto_cleanup": true}

# Déclencher cleanup manuel
POST /api/v2/system/audit/cleanup
```

### Certificate Expiry Alerts
```bash
# Obtenir config alertes
GET /api/v2/system/alerts/expiry

# Modifier alertes
PUT /api/v2/system/alerts/expiry
{"enabled": true, "alert_days": [30, 14, 7, 1]}

# Lister certificats expirants
GET /api/v2/system/alerts/expiring-certs?days=30

# Déclencher vérification manuelle
POST /api/v2/system/alerts/expiry/check
```

### Rate Limiting Config
```bash
# Obtenir config et stats
GET /api/v2/system/security/rate-limit

# Modifier config
PUT /api/v2/system/security/rate-limit
{"enabled": true, "whitelist_add": ["192.168.1.1"]}

# Reset compteurs
POST /api/v2/system/security/rate-limit/reset
```

### Encryption Management
```bash
# Statut chiffrement
GET /api/v2/system/security/encryption-status

# Générer nouvelle clé
GET /api/v2/system/security/generate-key

# Chiffrer toutes les clés existantes
POST /api/v2/system/security/encrypt-all-keys
{"dry_run": false}
```

## 📖 Documentation détaillée par module

Pour la documentation complète de chaque endpoint avec:
- Paramètres requis/optionnels
- Schémas de réponse
- Exemples de requêtes
- Codes d'erreur spécifiques

Consultez:
1. **Swagger UI**: `https://your-server:8443/api/docs` (recommandé)
2. **Fichier Markdown**: `/root/ucm-src/API_v2_COMPLETE.md`

## 🛠️ Outils de test

### Swagger UI
Interface web complète avec formulaires de test pour chaque endpoint.

### cURL
```bash
# Définir le token
export TOKEN="your-jwt-token"

# Utiliser dans les requêtes
curl -H "Authorization: Bearer $TOKEN" https://localhost:8443/api/v2/cas
```

### Postman/Insomnia
1. Importer la définition OpenAPI depuis `/api/docs/openapi.json`
2. Configurer l'authentification Bearer Token
3. Tester les endpoints

## 📝 Notes de version

### v2.0.0
- ✅ 121 endpoints RESTful
- ✅ Documentation Swagger/OpenAPI intégrée
- ✅ Support ACME avec sélection CA
- ✅ Proxy Let's Encrypt
- ✅ Authentification JWT
- ✅ Export multi-format (PEM, DER, PKCS12, JKS)
- ✅ Renouvellements automatiques
- ✅ Logs d'activité détaillés
- ✅ Monitoring système complet

## 🆘 Support

Pour toute question ou problème:
1. Vérifier la documentation Swagger UI
2. Consulter le fichier API_v2_COMPLETE.md
3. Vérifier les logs: `journalctl -u ucm -f`
4. Contacter le support technique

---

**Dernière mise à jour**: 23 janvier 2026  
**Version API**: v2.0.0  
**Service systemd**: `ucm.service`
