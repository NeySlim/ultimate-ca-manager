# ACME — Vhost public, URLs directory et certificats wildcard

UCM peut annoncer des URLs ACME publiques distinctes de l’URL d’administration.
Ce document décrit la topologie recommandée (noms `example.com` uniquement),
les règles des certificats wildcard, le plan de test et les commandes pytest.

Voir aussi : [ACME-PROXY-MULTI-CA.md](./ACME-PROXY-MULTI-CA.md), [ACME-DNS-PROPAGATION.md](./ACME-DNS-PROPAGATION.md).

## Topologie de référence

Dans le cas courant, admin et ACME sont des **sous-domaines de `ucm.example.com`** :

| Rôle | FQDN | Usage |
|------|------|--------|
| **Admin UCM** | `https://admin.ucm.example.com:8443` | GUI, API session, mTLS client optionnel/obligatoire |
| **ACME public** | `https://acme.ucm.example.com:8443` | `/acme/*` (CA locale) et `/acme/proxy/*` (proxy vers CA externe) |
| **URL de base UCM** (Paramètres → Général) | `https://admin.ucm.example.com` | Liens absolus, notifications, SAML |

Le listener UCM (gunicorn) est unique ; en production, un **reverse proxy** (F5, nginx, Traefik) termine TLS par **vhost** et route vers le backend UCM.

### Paramètres UCM (Paramètres → Général)

| Clé `SystemConfig` | Exemple | Effet |
|--------------------|---------|--------|
| `acme_proxy_vhost` | `acme.ucm.example.com` | Hostname dans les URLs du directory ACME (`newOrder`, `newNonce`, …) |
| `acme_proxy_port` | `8443` | Port dans ces URLs (omis si `443`) |
| `acme_proxy_tls_cert_id` | ID certificat UCM | **Métadonnée** : cert TLS à déployer sur le vhost ACME côté proxy (non appliqué au runtime gunicorn) |

Sans `acme_proxy_vhost`, UCM retombe sur `scheme://Host` de la requête entrante.

## Certificats wildcard — règles essentielles

Un SAN wildcard `*.ucm.example.com` couvre **un seul** label à gauche de `ucm.example.com` :

| Hostname accédé | Cert `*.ucm.example.com` | Cert `*.example.com` |
|-----------------|--------------------------|----------------------|
| `admin.ucm.example.com` | ✅ | ❌ |
| `acme.ucm.example.com` | ✅ | ❌ |
| `api.ucm.example.com` | ✅ | ❌ |
| `ucm.example.com` (apex) | ❌ | ❌ |
| `acme.example.com` | ❌ | ✅ |

**Cas typique UCM** : un certificat wildcard `*.ucm.example.com` suffit pour **les deux** vhosts
`admin.ucm.example.com` et `acme.ucm.example.com`, à condition que le reverse proxy présente
ce même certificat (ou des copies) sur chaque vhost SNI.

Ce wildcard **ne couvre pas** l’apex `ucm.example.com` — il faut un SAN explicite si ce nom est utilisé.

### Erreurs fréquentes

1. **Appliquer `*.ucm.example.com` puis accéder via `ucm.example.com`**  
   L’apex n’est pas couvert par le wildcard → **hostname mismatch**.

2. **Configurer `acme_proxy_vhost=acme.ucm.example.com` mais DNS/TLS sur un autre nom**  
   (ex. `acme.example.com` hors zone `ucm`) → timeout ou erreur TLS côté Certbot.

3. **Un seul listener gunicorn avec un cert admin, URLs directory pointant vers `acme.ucm.example.com`**  
   Les clients ACME vérifient le cert du hostname annoncé dans le directory, pas celui de l’admin.

4. **Confondre URL directory et certificat serveur**  
   Les URLs dans le directory suivent `acme_proxy_vhost` ; le client ACME valide le TLS **de chaque URL** annoncée.

### Stratégies TLS recommandées

**Option A — Wildcard `*.ucm.example.com` (recommandé si les deux vhosts sont sous `ucm.example.com`)**

```
admin.ucm.example.com:8443  → cert *.ucm.example.com (mTLS selon politique admin)
acme.ucm.example.com:8443   → même cert *.ucm.example.com, sans mTLS client
```

**Option B — SAN explicites**

```
SAN: admin.ucm.example.com, acme.ucm.example.com
```

**Option C — Lab / single-node (temporaire)**

Même FQDN pour admin et ACME le temps de valider le flux, puis scinder les vhosts.

> `*.example.com` ne remplace pas `*.ucm.example.com` pour `admin.ucm.example.com` /
> `acme.ucm.example.com` : ces noms ont **deux** labels avant `example.com`.

## Configuration exemple

### UCM (GUI ou API)

```http
PATCH /api/v2/settings/general
{
  "base_url": "https://admin.ucm.example.com",
  "acme_proxy_vhost": "acme.ucm.example.com",
  "acme_proxy_port": 8443,
  "acme_proxy_tls_cert_id": 42
}
```

`acme_proxy_tls_cert_id` référence le certificat wildcard (ou dédié) géré dans UCM à installer sur le vhost `acme.ucm.example.com` du reverse proxy.

### DNS

```
admin.ucm.example.com.  A     203.0.113.10
acme.ucm.example.com.   A     203.0.113.10
```

Même IP possible ; le proxy distingue par **SNI / Host**.

### Certbot (proxy multi-CA)

```bash
certbot certonly \
  --server https://acme.ucm.example.com:8443/acme/proxy/actalis-production/directory \
  --preferred-challenges dns-01 \
  --authenticator manual \
  --manual-auth-hook /path/to/auth.sh \
  --manual-cleanup-hook /path/to/cleanup.sh \
  --non-interactive --agree-tos \
  -m operator@example.com \
  -d app.example.com
```

Prérequis : `acme.ucm.example.com` résout vers le proxy, cert TLS valide pour ce nom (wildcard `*.ucm.example.com` ou SAN explicite), pas de mTLS client requis sur ce vhost.

## Tests automatisés (pytest)

### Suite ciblée (non-régression vhost public)

```bash
cd backend
python -m pytest tests/test_acme_public_url.py -q
python -m pytest tests/test_acme.py::TestAcmeServerSettings::test_get_settings_exposes_configured_public_acme_base_url \
  tests/test_acme.py::TestAcmeClientSettings::test_get_client_settings_exposes_configured_public_acme_urls \
  -q
```

### Couverture

| Fichier | Scénarios |
|---------|-----------|
| `test_acme_public_url.py` | `get_acme_public_origin`, port 443 vs non défaut, fallback Host, **table wildcard SAN**, directory `/acme` et `/acme/proxy` |
| `test_acme.py` | Settings API `acme_public_base_url` / `acme_proxy_public_base_url` |

### Commande suite ACME élargie

```bash
cd backend
python -m pytest tests/test_acme_public_url.py \
  tests/test_acme_proxy_ca_account.py \
  tests/test_acme_dns_selfcheck.py \
  tests/test_acme.py::TestAcmeServerSettings \
  tests/test_acme.py::TestAcmeClientSettings \
  tests/test_acme.py::TestAcmeClientProxy \
  -q
```

## Plan de test manuel

### 1. Paramètres généraux

1. Paramètres → Général : `acme_proxy_vhost` = `acme.ucm.example.com`, port `8443`
2. Enregistrer → recharger la page → valeurs persistées
3. ACME → Configuration : directory `https://acme.ucm.example.com:8443/acme/directory`
4. ACME → Let's Encrypt : proxy `https://acme.ucm.example.com:8443/acme/proxy/...`

### 2. DNS et TLS (wildcard `*.ucm.example.com`)

1. `dig +short acme.ucm.example.com` → IP du proxy attendue
2. `openssl s_client -connect acme.ucm.example.com:8443 -servername acme.ucm.example.com`  
   → SAN `*.ucm.example.com` ou `acme.ucm.example.com`
3. Répéter pour `admin.ucm.example.com` avec le même certificat wildcard
4. `curl -sk https://acme.ucm.example.com:8443/acme/proxy/directory` → JSON directory, URLs cohérentes

### 3. Séparation admin / ACME

1. Vhost admin : mTLS selon politique
2. Vhost ACME : **pas** de mTLS client obligatoire
3. Même cert wildcard acceptable sur les deux vhosts proxy

### 4. Certbot E2E

1. Compte proxy activé (slug ex. `actalis-production`)
2. `--server https://acme.ucm.example.com:8443/acme/proxy/<slug>/directory`
3. Attendu : enregistrement compte OK, challenge DNS-01 soumis

### 5. Régression apex wildcard

1. Certificat SAN=`*.ucm.example.com` seulement
2. `https://ucm.example.com` → **doit** échouer (apex non couvert)
3. `https://admin.ucm.example.com` et `https://acme.ucm.example.com` → **doivent** réussir

## Critères d’acceptation

- [ ] `acme_public_base_url` utilise `acme.ucm.example.com` configuré
- [ ] Un cert `*.ucm.example.com` couvre admin **et** ACME
- [ ] Certbot atteint le directory sans timeout ni hostname mismatch
- [ ] Tests `test_acme_public_url.py` verts
- [ ] Uniquement des noms `example.com` dans la doc

## Dépannage

| Symptôme | Cause probable | Action |
|----------|----------------|--------|
| `ConnectTimeout` vers `acme.ucm.example.com` | DNS / pare-feu | Corriger A/AAAA, ouvrir :8443 |
| `Hostname mismatch` sur admin | Apex ou mauvais wildcard | Vérifier SAN ; apex requiert SAN dédié |
| Certbot OK en local, KO à distance | DNS `acme.ucm.example.com` incorrect | Aligner DNS public |
| GUI OK après changement cert HTTPS | Cert appliqué sur listener unique | Split vhost proxy ou restaurer cert admin |
