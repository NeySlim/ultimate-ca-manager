# ACME Proxy Multi-CA — Plan de test

Feature: le proxy ACME réutilise les comptes `AcmeClientAccount` (même registre que le client ACME). Chaque compte peut exposer un endpoint dédié `/acme/proxy/<slug>/directory` en plus du chemin legacy `/acme/proxy/directory`.

## Prérequis lab

- UCM déployé avec migrations `050_acme_proxy_ca_account_link` et `051_acme_proxy_slug`
- Au moins un compte CA externe enregistré (ex. Actalis, Let's Encrypt Staging)
- Domaine configuré dans **ACME Domains** avec fournisseur DNS (ex. Gandi)
- Droits `read:acme` / `write:acme`

## Tests automatisés (non-régression)

```bash
cd backend
python -m pytest tests/test_acme_proxy_ca_account.py \
  tests/test_acme_proxy_key_encrypted.py \
  tests/test_acme.py::TestAcmeClientProxy \
  tests/test_acme.py::TestAcmeClientSettings \
  -q
```

Couverture ciblée :

| Fichier | Scénarios |
|---------|-----------|
| `test_acme_proxy_ca_account.py` | Résolution compte, API settings, binding service, **multi-path** (`TestProxyMultiPath`) |
| `test_acme_proxy_key_encrypted.py` | Chiffrement clé sur `AcmeClientAccount` |
| `test_acme.py` | Register/unregister proxy par `acme_account_id`, champs settings |

Suite complète lab (référence 2026-07-06) :

```bash
cd /opt/ucm/backend && runuser -u ucm -- /opt/ucm/venv/bin/python -m pytest tests/ -q
# Attendu : 2115 passed, 6 skipped
```

## Tests manuels — UI

### 1. Sélection compte CA (proxy global)

1. ACME → Let's Encrypt → section **Proxy ACME**
2. Activer le proxy
3. Vérifier le sélecteur **Compte CA en amont** liste les comptes de **Comptes CA externes**
4. Choisir un compte → l'URL directory s'affiche sous le sélecteur
5. Recharger la page → sélection persistée

### 2. Endpoint dédié par compte (slug)

1. **Comptes CA externes** → éditer un compte (ex. Actalis Production)
2. Activer **Exposer via le proxy ACME**
3. Définir un slug unique (ex. `actalis-production`) — pas de slug réservé (`directory`, `challenge`, …)
4. Enregistrer → badge `/acme/proxy/actalis-production/directory` sur la carte compte
5. Section proxy → **URL proxy dédiée** + liste **Tous les endpoints proxy activés**
6. Copier l'URL → `curl -sk …/acme/proxy/actalis-production/directory` renvoie le directory upstream

### 3. Test connexion

1. Avec un compte sélectionné, cliquer **Tester la connexion**
2. Attendu : ✓ connecté + nom CA
3. Sans compte sélectionné : bouton désactivé

### 4. Enregistrement upstream

1. Sélectionner un compte non enregistré (`is_registered: false`)
2. Saisir un email public (ex. `you@gmail.com`)
3. **Enregistrer le compte** → succès, badge « Compte enregistré »
4. Vérifier dans **Comptes CA externes** que le même compte affiche enregistré

### 5. Bascule entre CAs

1. Créer 2 comptes avec slugs distincts (Staging + Production)
2. Enregistrer les deux
3. Certbot / curl sur chaque slug → directory et émetteur cohérents avec le compte lié

### 6. Reset compte

1. Compte enregistré → icône reset (↻)
2. Confirmer → `account_url` / clé effacés sur le compte lié
3. Ré-enregistrer possible

## Tests manuels — API

```bash
# Settings
curl -sk -H "Authorization: Bearer $TOKEN" \
  https://ucm.example:8443/api/v2/acme/client/settings | jq '.data | {proxy_acme_account_id, proxy_upstream_url, proxy_account_registered}'

# Activer proxy + slug sur compte id=4
curl -sk -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"proxy_enabled":true,"proxy_slug":"actalis-production"}' \
  https://ucm.example:8443/api/v2/acme/client/accounts/4

# Directory par slug (sans auth)
curl -sk https://ucm.example:8443/acme/proxy/actalis-production/directory | jq .

# Directory legacy (compte sélectionné dans settings)
curl -sk https://ucm.example:8443/acme/proxy/directory | jq .

# Test connexion
curl -sk -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"acme_account_id":4}' \
  https://ucm.example:8443/api/v2/acme/client/proxy/test-connection
```

## Tests manuels — Proxy ACME E2E (Certbot)

Exemple validé en environnement lab (UCM + CA externe + fournisseur DNS) :

```bash
TEST_DOMAIN="cert-proxy-test.example.com"   # sous-domaine neuf à chaque run
CFG="/tmp/certbot-proxy-path"
rm -rf "$CFG" && mkdir -p "$CFG"/{config,work,logs}

certbot certonly \
  --config-dir "$CFG/config" \
  --work-dir "$CFG/work" \
  --logs-dir "$CFG/logs" \
  --server https://<ucm-host>:8443/acme/proxy/<slug>/directory \
  --no-verify-ssl \
  --preferred-challenges dns-01 \
  --authenticator manual \
  --manual-auth-hook /bin/true \
  --manual-cleanup-hook /bin/true \
  --non-interactive --agree-tos \
  -m you@example.com \
  -d "$TEST_DOMAIN"

openssl x509 -in "$CFG/config/live/$TEST_DOMAIN/cert.pem" -noout -issuer -subject
```

Notes E2E :

- UCM crée/supprime les TXT via le fournisseur DNS configuré ; les hooks Certbot peuvent rester `/bin/true`
- Échec intermittent `unauthorized` : propagation DNS Actalis (~30 s) — réessayer avec un FQDN neuf
- Logs : `/var/log/ucm/ucm.log` (lignes `[ACME Proxy BG]`)

## Migration legacy (upgrade)

1. Migration **050** : lie `acme.proxy.acme_account_id` au registre `AcmeClientAccount`
2. Migration **051** : colonnes `proxy_slug`, `proxy_enabled` ; backfill slug pour le compte proxy configuré
3. Vérifier en DB : `SELECT id,label,proxy_slug,proxy_enabled FROM acme_client_accounts`
4. `/acme/proxy/directory` reste compatible ; nouveaux clients peuvent cibler `/acme/proxy/<slug>/directory`

## Critères d'acceptation

- [x] Sélection multi-CA dans l'UI proxy
- [x] Un seul registre de comptes (pas de duplication EAB proxy)
- [x] Endpoint dédié par compte (`proxy_slug` + `proxy_enabled`)
- [x] Rétrocompat `/acme/proxy/directory`
- [x] Tests pytest ciblés + suite lab verte
- [x] E2E Certbot via slug (CA externe + fournisseur DNS)
- [x] i18n 9 langues + guides d'aide + aide contextuelle GUI
