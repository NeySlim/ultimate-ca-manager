# ❓ FAQ - Questions Fréquemment Posées

---

## 🔐 Sécurité et PKI

### Quelle est la différence entre Root CA et Intermediate CA ?

**Root CA** (Autorité racine):
- Au sommet de la hiérarchie PKI
- Auto-signée
- Validité longue (20-30 ans)
- **Doit être stockée hors ligne** (cold storage)
- Utilisée uniquement pour signer les Intermediate CAs

**Intermediate CA** (Autorité intermédiaire):
- Signée par la Root CA
- Utilisée pour les émissions quotidiennes
- Validité moyenne (5-10 ans)
- Peut être révoquée sans affecter d'autres Intermediate CAs
- **Online**, accessible pour émissions

**Pourquoi cette séparation ?**
- Sécurité: Si Intermediate compromise, seule elle est révoquée
- Root CA reste en sécurité hors ligne
- Permet de créer des CAs pour différents usages

---

### Dois-je vraiment stocker ma Root CA hors ligne ?

**Oui, absolument** pour une PKI de production !

**Bonnes pratiques**:
```
1. Créer Root CA dans UCM
2. Exporter immédiatement (PKCS#12 avec mot de passe fort)
3. Sauvegarder sur:
   - Clé USB chiffrée → coffre-fort physique
   - HSM (Hardware Security Module)
   - Backup chiffré hors site
4. Créer Intermediate CA(s)
5. SUPPRIMER la Root CA de UCM (ou serveur dédié offline)
```

**Pour environnements de test/dev**:
- Garder Root CA online est acceptable
- Marquer clairement comme "TEST" dans le CN

---

### Quelle longueur de clé utiliser ?

**Recommandations 2026**:

| Usage | Algorithme | Longueur | Commentaire |
|-------|-----------|----------|-------------|
| Root CA | RSA | 4096 bits | Maximum sécurité |
| Intermediate CA | RSA | 4096 bits | Sécurité + compatibilité |
| Certificats serveur | RSA | 2048 bits | Standard actuel |
| Certificats serveur | ECDSA | P-256 | Moderne, plus rapide |
| Certificats client | RSA | 2048 bits | Compatible partout |
| Code signing | RSA | 4096 bits | Sécurité maximale |
| IoT/Embedded | ECDSA | P-256 | Faible consommation |

**ECDSA vs RSA**:
- ECDSA P-256 ≈ RSA 3072 (sécurité équivalente)
- ECDSA plus rapide, clés plus petites
- Mais moins compatible (vieux systèmes)

---

### Quelle validité pour mes certificats ?

**Limites navigateurs (2026)**:
- Maximum: **398 jours** (13 mois)
- Recommandé: **90-180 jours** (auto-renouvellement)

**Certificats CAs**:
- Root CA: 20-30 ans
- Intermediate CA: 5-10 ans

**Autres certificats**:
- Serveurs web: 90-398 jours
- Clients: 1-3 ans
- Code signing: 1-3 ans
- IoT: 1-5 ans (selon use case)

**Tendance**: Validités de plus en plus courtes pour sécurité

---

## 🔄 SCEP

### SCEP vs enrollment manuel, quand utiliser quoi ?

**Utiliser SCEP quand**:
- Nombreux devices (>10)
- Devices mobiles (iOS, Android)
- Renouvellement automatique souhaité
- Environnement MDM (Mobile Device Management)
- IoT / embedded devices
- Déploiement réseau à grande échelle

**Enrollment manuel quand**:
- Peu de certificats (<10)
- Serveurs individuels
- Besoin de contrôle strict
- Certificats avec configurations custom

---

### Mon iPhone rejette le profil SCEP, pourquoi ?

**Causes courantes**:

1. **Certificat UCM non de confiance**
   ```
   Solution: Installer d'abord le Root CA sur iOS
   Settings → General → VPN & Device Management → Install Profile
   ```

2. **URL avec IP au lieu de FQDN**
   ```
   ❌ https://192.168.1.100:8443/scep/mobile
   ✅ https://pki.example.com:8443/scep/mobile
   ```

3. **Challenge password incorrect**
   ```
   Utiliser "Generate enrollment URL" dans UCM
   QR Code recommandé pour éviter erreurs de frappe
   ```

4. **Port HTTPS non accessible**
   ```
   Tester depuis Safari: https://pki.example.com:8443
   Vérifier firewall
   ```

---

### Le renouvellement automatique SCEP ne fonctionne pas

**Checklist**:
- [ ] Auto-renewal activé dans l'endpoint SCEP
- [ ] Renewal window configuré (ex: 30 jours)
- [ ] Device a accès réseau à UCM
- [ ] Certificat HTTPS UCM toujours valide
- [ ] Logs SCEP: `/opt/ucm/logs/scep.log`

**Test manuel**:
```bash
# Forcer renouvellement immédiat
# Modifier temporairement validity du certificat existant
# pour le faire expirer dans <30 jours
```

---

## 💾 Base de Données

### SQLite ou PostgreSQL ?

**SQLite** (défaut):
- ✅ Installation simple
- ✅ Pas de serveur séparé
- ✅ Parfait pour <2000 certificats
- ❌ Locks en écriture concurrente
- ❌ Performance limitée

**PostgreSQL**:
- ✅ Haute performance
- ✅ Écritures concurrentes
- ✅ Scalable (>100k certificats)
- ✅ Réplication, backups avancés
- ❌ Serveur séparé nécessaire

**Recommandation**:
- Dev/Test: SQLite
- Production <2000 certs: SQLite OK
- Production >2000 certs: PostgreSQL
- Enterprise: PostgreSQL

---

### Comment migrer de SQLite vers PostgreSQL ?

Voir: [Migration vers PostgreSQL](Migration-Guide#sqlite-to-postgresql)

**Résumé**:
```bash
# Utiliser docker-compose.postgres.yml
docker-compose -f docker-compose.postgres.yml up -d

# UCM détecte automatiquement PostgreSQL
# Migration automatique des données
```

---

### À quelle fréquence faire des backups ?

**Recommandations**:

**Backup complet**:
- Quotidien minimum
- Avant toute opération critique (upgrade, etc.)
- Rétention: 7-30 jours

**Backup Root CA** (si online):
- Après chaque modification
- Stockage sécurisé, multiple copies
- Test de restauration régulier

**Automatique avec UCM**:
```bash
# UCM backup automatique quotidien
/opt/ucm/backups/ucm-backup-YYYY-MM-DD.db

# Configurable dans Settings → System → Backup
```

---

## 🌐 Déploiement

### Quel port utiliser : 8443 ou 443 ?

**8443** (défaut UCM):
- ✅ Pas besoin de root
- ✅ Peut coexister avec autre serveur web
- ❌ URL moins standard (https://host:8443)

**443** (standard HTTPS):
- ✅ URL standard (https://host)
- ❌ Nécessite root ou capability CAP_NET_BIND_SERVICE
- ❌ Conflit avec autre serveur web

**Solution recommandée**:
```
Reverse proxy (nginx, Traefik, HAProxy)
Internet:443 → Proxy → UCM:8443

Avantages:
- URL standard
- Load balancing possible
- Rate limiting
- WAF (Web Application Firewall)
```

---

### UCM derrière un reverse proxy ?

**Oui, configuration recommandée !**

**Exemple nginx**:
```nginx
server {
    listen 443 ssl http2;
    server_name pki.example.com;
    
    ssl_certificate /etc/ssl/certs/pki.example.com.crt;
    ssl_certificate_key /etc/ssl/private/pki.example.com.key;
    
    location / {
        proxy_pass https://localhost:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**UCM configuration**:
```bash
# .env
PREFERRED_URL_SCHEME=https
FORCE_HTTPS=true
```

---

### Peut-on déployer UCM en haute disponibilité (HA) ?

**Oui, avec quelques considérations**:

**Architecture HA**:
```
                Load Balancer
                     |
        +------------+------------+
        |                         |
    UCM Node 1              UCM Node 2
        |                         |
        +------------+------------+
                     |
              PostgreSQL
          (avec réplication)
```

**Prérequis**:
- PostgreSQL (pas SQLite)
- Stockage partagé pour `/data` (NFS, S3, etc.)
- Session store externe (Redis)
- Load balancer (HAProxy, nginx)

**Limitations**:
- Clés privées partagées (sécurité)
- Complexité accrue
- Overhead pour <10k certs

**Recommandation**: 
- <10k certs: Single node + backups
- >10k certs: HA setup

---

## 🔧 Opérations

### Comment révoquer un certificat en urgence ?

**Via UI** (recommandé):
```
1. Certificates → Search (serial ou CN)
2. Actions → Revoke
3. Reason: Key Compromise
4. Confirm

Effet immédiat:
- Ajouté à CRL
- OCSP répond "revoked"
```

**Via CLI** (si UI inaccessible):
```bash
cd /opt/ucm
source venv/bin/activate
python3 << EOF
from app import create_app, db
from app.models import Certificate
from app.services.certificate_service import revoke_certificate

app = create_app()
with app.app_context():
    cert = Certificate.query.filter_by(serial_number='1A2B3C4D').first()
    revoke_certificate(cert.id, reason='key_compromise')
    print(f"Certificate {cert.serial_number} revoked")
EOF
```

---

### La CRL grandit trop, que faire ?

**Options**:

1. **Delta CRL** (pas encore implémenté dans UCM v1.0.1)

2. **Purger anciennes révocations**
   ```
   Settings → CRL → Auto-cleanup
   Retirer certificats révoqués expirés depuis >90 jours
   ```

3. **Réduire CRL lifetime**
   ```
   Next Update: 24h au lieu de 7 jours
   Mais augmente charge serveur
   ```

4. **Préférer OCSP**
   ```
   Activer OCSP responder
   Clients modernes préfèrent OCSP
   CRL comme fallback uniquement
   ```

---

### Comment tester mon certificat ?

**Test serveur web**:
```bash
# SSL Labs (online)
https://www.ssllabs.com/ssltest/analyze.html?d=example.com

# OpenSSL
openssl s_client -connect example.com:443 -showcerts

# Vérifier chaîne
openssl verify -CAfile chain.pem cert.pem
```

**Test OCSP**:
```bash
openssl ocsp \
  -issuer intermediate-ca.pem \
  -cert cert.pem \
  -url http://ocsp.example.com:8080 \
  -CAfile root-ca.pem
```

**Test CRL**:
```bash
curl http://pki.example.com:8080/crl/ca-123.crl -o crl.der
openssl crl -in crl.der -inform DER -text -noout
```

---

## 📱 Compatibilité

### Quels systèmes supportent SCEP ?

**Supportés nativement**:
- ✅ iOS / iPadOS (toutes versions)
- ✅ macOS (10.7+)
- ✅ Android (avec app tierce ou MDM)
- ✅ Windows (via NDES/Intune)
- ✅ Cisco routers/switches
- ✅ Palo Alto firewalls
- ✅ Juniper devices
- ✅ F5 load balancers

**Avec apps tierces**:
- Linux (OpenSCEP, sscep)
- OpenWrt / embedded

---

### UCM fonctionne sur Windows ?

**Pas directement**, mais options:

1. **WSL2** (Windows Subsystem for Linux)
   ```powershell
   wsl --install
   # Puis installer UCM dans WSL Ubuntu
   ```

2. **Docker Desktop** (recommandé)
   ```powershell
   # Installer Docker Desktop
   docker-compose up -d
   ```

3. **VM Linux** (VirtualBox, Hyper-V)

**Clients Windows** peuvent utiliser UCM (via navigateur/API)

---

## 🆘 Support

### J'ai trouvé un bug, où le signaler ?

**GitHub Issues**: https://github.com/NeySlim/ultimate-ca-manager/issues

**Inclure**:
- Version UCM (`ucm --version` ou About page)
- OS et version
- Steps pour reproduire
- Logs d'erreur
- Screenshots si pertinent

---

### Où demander de l'aide ?

1. **Documentation Wiki** (vous êtes ici !)
2. **[Troubleshooting](Troubleshooting)** - Problèmes courants
3. **[GitHub Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)** - Questions générales
4. **[GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)** - Bugs

---

### UCM est-il gratuit ?

**Oui !** UCM est open source sous licence BSD-3-Clause.

- ✅ Utilisation gratuite (personnel, entreprise)
- ✅ Modification autorisée
- ✅ Distribution autorisée
- ✅ Pas de limite de certificats
- ✅ Support communautaire

**Support commercial**: Pas encore disponible (v1.0.1)

---

**Plus de questions ?** → [GitHub Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)
