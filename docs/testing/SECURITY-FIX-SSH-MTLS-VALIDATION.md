# Plan de test et validation — correctif sécurité SSH hostname + mTLS PKCS#12

**Branche** : `fix/security-ssh-hostname-mtls-pkcs12`  
**Cible** : environnement de test lab privé (UCM `2.182-rc3-mtls-pem-p12`)  
**Findings couverts** :

| Sévérité | Description | Fichiers |
|----------|-------------|----------|
| Élevée | Injection commande via `?hostname=` non validé sur `GET /ssh/setup/<refid>` | `backend/api/ssh_setup.py`, `backend/api/v2/ssh/validation.py` |
| Moyenne | Mot de passe PKCS#12 mTLS exposé en query string GET | `backend/api/v2/mtls.py`, `frontend/src/services/mtls.service.js` |

---

## 1. Prérequis déploiement

| Élément | Attendu |
|---------|---------|
| Fichiers backend | `api/v2/ssh/validation.py`, `api/ssh_setup.py`, `api/v2/ssh/script_routes.py`, `api/v2/ssh/setup_scripts_win.py` |
| Tests | `tests/test_ssh_setup_public.py`, `tests/test_ssh_setup_validation.py` |
| Service | `systemctl status ucm` → **active** |
| Health | `GET /health` → **200** |

Redémarrage après déploiement :

```bash
systemctl restart ucm
```

---

## 2. Tests automatisés (obligatoires)

Exécuter depuis la racine backend, en user applicatif (`ucm` sur une install standard) :

```bash
cd /opt/ucm/backend   # ou <UCM_ROOT>/backend en dev

python -m pytest \
  tests/test_ssh_setup_public.py \
  tests/test_ssh_setup_validation.py \
  tests/test_mtls.py::TestMTLSCertificates::test_download_pkcs12_requires_post \
  -v
```

### Matrice de cas

| ID | Cas | Fichier | Attendu |
|----|-----|---------|---------|
| T1 | Injection `$(id)` dans `hostname` | `test_ssh_setup_public.py` | **400** + corps contenant `Invalid hostname format` |
| T2 | Quote breakout `x";id;"` | `test_ssh_setup_public.py` | **400** |
| T3 | Hostname valide `web01.example.com` | `test_ssh_setup_public.py` | **200** + `HOSTNAME="web01.example.com"` dans le script |
| T4 | Regex et messages d'erreur | `test_ssh_setup_validation.py` | **pass** |
| T5 | PKCS#12 via GET | `test_mtls.py` | **405** (POST requis) |

Critère de sortie : **7/7 passed**.

---

## 3. Tests manuels HTTP (optionnels)

La route `/ssh/setup/` est exemptée du redirect HTTPS forcé (clients SSH sans suivi de redirect). Les tests pytest utilisent le client Flask in-process ; les vérifications curl ci-dessous complètent la validation sur un lab réel.

### 3.1 SSH setup public

Prérequis : une SSH CA de type **host** existante ; noter son `refid`.

```bash
LAB="https://<fqdn-ou-host-lab>:8443"
REFID="<refid-ssh-ca-host>"

# Injection — doit être rejetée
curl -sk "${LAB}/ssh/setup/${REFID}?type=host&hostname=\$(id)"
# → 400

# Hostname valide — script bash généré
curl -sk "${LAB}/ssh/setup/${REFID}?type=host&hostname=web01.example.com"
# → 200, corps contenant HOSTNAME="web01.example.com"
```

### 3.2 mTLS PKCS#12 (session authentifiée)

```bash
CERT_ID="<id-certificat-mtls>"

# GET interdit
curl -sk -b cookies.txt \
  "${LAB}/api/v2/mtls/certificates/${CERT_ID}/download?format=pkcs12&password=secret"
# → 405

# POST attendu
curl -sk -b cookies.txt -X POST \
  -H "Content-Type: application/json" \
  -d '{"password":"secret"}' \
  "${LAB}/api/v2/mtls/certificates/${CERT_ID}/download?format=pkcs12" \
  -o cert.p12
# → 200, Content-Type application/x-pkcs12
```

---

## 4. Résultats de validation (lab privé)

**Date** : 2026-07-03  
**Version lab** : `2.182-rc3-mtls-pem-p12`

| Contrôle | Résultat |
|----------|----------|
| Déploiement (`validate_setup_hostname` dans `ssh_setup.py`) | OK |
| Service `ucm` | **active** |
| Pytest sécurité (T1–T5) | **7 passed** (~1,2 s) |
| Health HTTPS (`GET /health`) | **200** |
| E2E curl manuel | Non exécuté (`curl` absent sur le lab ; couvert par pytest in-process) |

**Conclusion** : correctif **validé** sur l'environnement de test lab privé via la suite pytest. Les scénarios d'injection SSH et la garde POST PKCS#12 sont couverts.

---

## 5. Checklist avant merge upstream

- [x] Tests unitaires backend passent sur le lab
- [x] Health OK après redémarrage
- [ ] PR ouverte vers `NeySlim/dev`
- [ ] Findings marqués résolus dans le suivi sécurité interne

---

## Références code

- Validation hostname : `backend/api/v2/ssh/validation.py` — pattern `^[a-zA-Z0-9._-]+$`
- Endpoint public : `backend/api/ssh_setup.py`
- Route authentifiée équivalente : `backend/api/v2/ssh/script_routes.py`
- Garde POST PKCS#12 : `backend/api/v2/mtls.py` (`test_download_pkcs12_requires_post`)
