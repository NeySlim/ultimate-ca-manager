# ACME — Vhost public, URLs directory et certificats wildcard

UCM peut annoncer des URLs ACME publiques distinctes de l’URL d’administration.
Ce document décrit la topologie recommandée (noms `example.com` uniquement),
les règles des certificats wildcard, le plan de test et les commandes pytest.

Voir aussi : [ACME-PROXY-MULTI-CA.md](./ACME-PROXY-MULTI-CA.md), [ACME-DNS-PROPAGATION.md](./ACME-DNS-PROPAGATION.md).

## Portée fonctionnelle (PR)

| Zone | Fichiers / comportement |
|------|-------------------------|
| **Backend** | `backend/utils/acme_public_url.py`, `get_acme_public_origin()` |
| **API ACME** | `acme_api.py`, `acme_proxy_api.py` — liens directory (`newOrder`, …) |
| **Settings API** | `api/v2/settings/general.py` — GET/PATCH `acme_public_*` |
| **Settings ACME** | `api/v2/acme/settings.py`, `api/v2/acme_client/settings.py` — `acme_public_base_url`, `acme_proxy_public_base_url` |
| **Frontend** | `GeneralSection.jsx`, `ConfigTab.jsx`, `LetsEncryptTab.jsx` |
| **i18n (9 langues)** | `frontend/src/i18n/locales/{en,fr,de,es,it,ja,pt,uk,zh}.json` — labels + helpers wildcard |
| **Aide contextuelle** | `helpContent.js` / `helpGuides.js` (en) + `help/{de,es,fr,it,ja,pt,uk,zh}/settings.js` |
| **Tests** | `backend/tests/test_acme_public_url.py`, extensions `test_acme.py` |

### Clés `SystemConfig`

| Clé | Validation | Effet runtime |
|-----|------------|---------------|
| `acme_public_vhost` | Hostname concret uniquement (pas de préfixe `*.`) | URLs directory ACME (serveur local **et** proxy) |
| `acme_public_port` | 1–65535 | Port dans les URLs (omis si 443) |
| `acme_public_tls_cert_id` | ID certificat UCM avec clé privée | Métadonnée ops (pas de push TLS automatique) |

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
| `acme_public_vhost` | `acme.ucm.example.com` | Hostname dans les URLs du directory ACME (`newOrder`, `newNonce`, …) |
| `acme_public_port` | `8443` | Port dans ces URLs (omis si `443`) |
| `acme_public_tls_cert_id` | ID certificat UCM | **Métadonnée** : cert TLS à déployer sur le vhost ACME côté proxy (non appliqué au runtime gunicorn) |

Sans `acme_public_vhost`, UCM retombe sur `scheme://Host` de la requête entrante.

> **Important** : configurez DNS et TLS pour le vhost ACME **avant** d’enregistrer ce champ.
> Dès qu’il est renseigné, les clients ACME qui relisent le directory (Certbot, renouvellements)
> basculent immédiatement vers les nouvelles URLs — un vhost injoignable casse les renouvellements.

> Le wildcard `*.ucm.example.com` est un concept **SAN TLS**, pas un hostname annonçable.
> La validation API **rejette** `*.ucm.example.com` comme valeur de `acme_public_vhost`.

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

2. **Configurer `acme_public_vhost=acme.ucm.example.com` mais DNS/TLS sur un autre nom**  
   (ex. `acme.example.com` hors zone `ucm`) → timeout ou erreur TLS côté Certbot.

3. **Un seul listener gunicorn avec un cert admin, URLs directory pointant vers `acme.ucm.example.com`**  
   Les clients ACME vérifient le cert du hostname annoncé dans le directory, pas celui de l’admin.

4. **Confondre URL directory et certificat serveur**  
   Les URLs dans le directory suivent `acme_public_vhost` ; le client ACME valide le TLS **de chaque URL** annoncée.

5. **Saisir `*.ucm.example.com` comme vhost**  
   Rejeté par l’API — produirait des URLs invalides (`https://*.ucm.example.com/...`).

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

### Reverse proxy — en-tête `Host`

Les vérifications JWS RFC 8555 comparent l’URL signée par le client à l’origine publique
configurée (`get_acme_public_origin`). Le serveur ACME local et le proxy utilisent la même origine
pour les liens directory **et** la validation JWS.

Si le reverse proxy ne transmet pas le `Host` public vers gunicorn, le proxy ACME accepte aussi
l’URL telle que vue par UCM (fallback) — mais **nginx / Traefik / F5** doivent idéalement
préserver le hostname client :

```nginx
# nginx — vhost ACME
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

Sans `proxy_set_header Host`, certains flux proxy peuvent échouer avec « URL mismatch »
lorsque le vhost public est configuré et que le client signe les URLs du directory.

## Configuration exemple

### UCM (GUI ou API)

```http
PATCH /api/v2/settings/general
{
  "base_url": "https://admin.ucm.example.com",
  "acme_public_vhost": "acme.ucm.example.com",
  "acme_public_port": 8443,
  "acme_public_tls_cert_id": 42
}
```

`acme_public_tls_cert_id` référence le certificat wildcard (ou dédié) géré dans UCM à installer sur le vhost `acme.ucm.example.com` du reverse proxy.

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

### Suite minimale (vhost public)

```bash
cd backend
python -m pytest tests/test_acme_public_url.py -q
# Attendu : 21 passed

python -m pytest \
  tests/test_acme.py::TestAcmeServerSettings::test_get_settings_exposes_configured_public_acme_base_url \
  tests/test_acme.py::TestAcmeClientSettings::test_get_client_settings_exposes_configured_public_acme_urls \
  -q
# Attendu : 2 passed
```

### Détail `test_acme_public_url.py`

| Classe | Scénarios |
|--------|-----------|
| `TestGetAcmePublicOrigin` | vhost+port configurés, port 443 omis, fallback `Host`, admin Host n’écrase pas le vhost ACME |
| `TestWildcardSanHostnameCompatibility` | Table SAN : `*.ucm.example.com` couvre `admin.ucm.example.com` **et** `acme.ucm.example.com` ; apex `ucm.example.com` non couvert ; `*.example.com` insuffisant pour les sous-domaines `ucm` |
| `TestAcmePublicVhostSettingsApi` | PATCH rejette `*.ucm.example.com`, accepte hostname concret |
| `TestProxyJwsExpectedUrls` | JWS proxy : origine publique configurée prioritaire sur `Host` entrant |
| `TestAcmeDirectoryPublicUrls` | `/acme/directory` et `/acme/proxy/directory` renvoient `newOrder` avec l’origine configurée |

### Couverture API settings

| Fichier | Scénarios |
|---------|-----------|
| `test_acme.py` | `acme_public_base_url`, `acme_proxy_public_base_url` après PATCH general settings |

### Commande suite ACME élargie (non-régression proxy)

```bash
cd backend
python -m pytest tests/test_acme_public_url.py \
  tests/test_acme_proxy_ca_account.py \
  tests/test_acme_dns_selfcheck.py \
  tests/test_acme.py::TestAcmeServerSettings \
  tests/test_acme.py::TestAcmeClientSettings \
  tests/test_acme.py::TestAcmeClientProxy \
  -q
# Référence locale : 90 passed
```

### Frontend (i18n)

```bash
cd frontend
npm run check:i18n
# Attendu : 4036 keys, 9/9 locales in sync (clés acmePublic*)
```

## Plan de test manuel

### 1. Paramètres généraux (GUI)

1. **Paramètres → Général** : renseigner
   - `acme_public_vhost` = `acme.ucm.example.com`
   - `acme_public_port` = `8443`
   - `acme_public_tls_cert_id` = ID d’un cert `*.ucm.example.com` (optionnel)
2. Enregistrer → recharger (`Ctrl+Shift+R`) → valeurs persistées
3. Vérifier les **helpers** (hostname concret, avertissement DNS/TLS) dans au moins **fr** et **en**
4. **ACME → Configuration** : directory `https://acme.ucm.example.com:8443/acme/directory`
5. **ACME → Let's Encrypt** : base proxy `https://acme.ucm.example.com:8443/acme/proxy/...`

### 2. API REST

```bash
# Lecture
curl -sk -b cookies.txt https://admin.ucm.example.com:8443/api/v2/settings/general \
  | jq '.data.acme_public_vhost, .data.acme_public_port'

curl -sk -b cookies.txt https://admin.ucm.example.com:8443/api/v2/acme/client/settings \
  | jq '.data.acme_public_base_url, .data.acme_proxy_public_base_url'

# Écriture (session admin)
curl -sk -b cookies.txt -X PATCH https://admin.ucm.example.com:8443/api/v2/settings/general \
  -H 'Content-Type: application/json' \
  -d '{"acme_public_vhost":"acme.ucm.example.com","acme_public_port":8443}'
```

Attendu après PATCH : les URLs ci-dessus reflètent `acme.ucm.example.com:8443`.

### 3. Aide contextuelle (9 langues UI / 8+1 help)

| Langue UI | Fichier aide panneau | Helpers i18n |
|-----------|---------------------|--------------|
| en | `helpContent.js` + `helpGuides.js` | `en.json` |
| fr, de, es, it, ja, pt, uk, zh | `help/<lang>/settings.js` | `<lang>.json` |

1. Ouvrir **Paramètres** → panneau d’aide flottant
2. Section **« Public ACME vhost »** (ou équivalent traduit) visible
3. Contenu : `admin.ucm.example.com`, `acme.ucm.example.com`, wildcard `*.ucm.example.com`, apex non couvert

### 4. DNS et TLS (wildcard `*.ucm.example.com`)

1. `dig +short acme.ucm.example.com` → IP du proxy attendue
2. `openssl s_client -connect acme.ucm.example.com:8443 -servername acme.ucm.example.com`  
   → SAN `*.ucm.example.com` ou `acme.ucm.example.com`
3. Répéter pour `admin.ucm.example.com` avec le **même** certificat wildcard
4. `curl -sk https://acme.ucm.example.com:8443/acme/proxy/directory` → JSON ; chaque URL utilise `acme.ucm.example.com`

### 5. Séparation admin / ACME (reverse proxy)

1. Vhost **admin** : mTLS selon politique (`mtls_required` si applicable)
2. Vhost **ACME** : pas de mTLS client obligatoire (Certbot / Actalis)
3. Même cert wildcard présenté sur les deux vhosts SNI

### 6. Certbot E2E

```bash
certbot certonly \
  --server https://acme.ucm.example.com:8443/acme/proxy/<slug>/directory \
  --preferred-challenges dns-01 \
  ...
```

Attendu : enregistrement compte OK ; échec uniquement si hook DNS absent ou TXT non publié.

### 7. Régressions wildcard connues

| Action | Résultat attendu |
|--------|------------------|
| Cert `*.ucm.example.com` sur vhost admin | `https://admin.ucm.example.com` OK |
| Même cert sur vhost ACME | `https://acme.ucm.example.com` OK |
| Accès apex `https://ucm.example.com` avec SAN wildcard seul | **Échec TLS** (apex non couvert) |
| Appliquer wildcard comme cert HTTPS unique gunicorn + directory vers `acme.ucm...` | Certbot **hostname mismatch** si cert ne matche pas l’URL directory |
| `acme_public_vhost` pointe vers un DNS injoignable | `ConnectTimeout` Certbot |

## Critères d’acceptation

- [ ] `acme_public_base_url` et `acme_proxy_public_base_url` utilisent `acme.ucm.example.com` configuré
- [ ] Un cert `*.ucm.example.com` couvre **admin** et **ACME** (pas l’apex)
- [ ] Certbot atteint le directory sans timeout ni hostname mismatch
- [ ] `pytest tests/test_acme_public_url.py` — 21 passed
- [ ] `npm run check:i18n` — 9 locales synchronisées
- [ ] Aide panneau + helpers mentionnent la topologie wildcard dans toutes les langues UI
- [ ] Doc et exemples : uniquement `example.com` (pas de FQDN lab)

## Dépannage

| Symptôme | Cause probable | Action |
|----------|----------------|--------|
| `ConnectTimeout` vers `acme.ucm.example.com` | DNS / pare-feu | Corriger A/AAAA, ouvrir :8443 |
| `Hostname mismatch` sur admin | Apex ou mauvais wildcard | Vérifier SAN ; apex requiert SAN dédié |
| Certbot OK en local, KO à distance | DNS `acme.ucm.example.com` incorrect | Aligner DNS public |
| GUI OK après changement cert HTTPS | Cert appliqué sur listener unique | Split vhost proxy ou restaurer cert admin |
