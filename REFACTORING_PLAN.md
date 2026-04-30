# UCM Refactoring Plan - v2.142-dev

**Branche :** `refactor`  
**Stratégie :** Commits directs, conservation historique Git  
**Développeur :** Lio (seul dev)  
**Priorité :** Maintenabilité > Performance  
**Règle UCM :** Fichiers 200-400l (800l max), haute cohésion, faible couplage

---

## 📋 Sommaire
- [Objectifs](#objectifs)
- [Règles](#règles)
- [Phases](#phases)
- [Tâches détaillées](#tâches-détaillées)
- [Progrès](#progrès)
- [Historique des commits](#historique-des-commits)

---

## 🎯 Objectifs

### Principal
Réduire la taille des fichiers > 800 lignes pour améliorer la maintenabilité.

### Secondaires
1. Supprimer les dépendances circulaires (services → api)
2. Séparer clairement les layers (Routes → Services → Models)
3. Centraliser la logique dupliquée (export, validation)
4. Améliorer la testabilité

---

## 📜 Règles

### ⚠️ CONTRAINTES UCM (à respecter absolument)
- **Taille fichiers :** 200-400 lignes (max 800)
- **Cohésion :** Haute (1 fichier = 1 responsabilité)
- **Couplage :** Faible (éviter imports circulaires)
- **Tests :** `pytest backend/tests/ -x -q` avant chaque commit
- **Historique :** **Conserver** (pas de squash, commits atomiques)
- **Commits :** Directs sur `refactor`, pas de PR

### 📝 Conventions de commit
```
refactor(backend): découper certificates.py en modules
refactor(backend): extraire export_service.py
fix(backend): corriger import circulaire dans acme_service
```

### 🔧 Workflow
1. Travailler sur `refactor` (déjà en place)
2. Commiter avec message clair
3. Pousher sur origin/refactor
4. Mettre à jour ce fichier REFACTORING_PLAN.md
5. Passer à la tâche suivante

---

## 🚀 Phases

### Phase 1: Backend API (Priorité HAUTE) ⬆️
**Objectif :** Découper les 6 fichiers API > 1000 lignes

| # | Fichier | Lignes | Statut | Commit prévu |
|---|--------|--------|--------|---------------|
| 1 | `api/v2/certificates.py` | 2220 | ⏳ | `refactor(backend): split certificates.py into modules` |
| 2 | `api/v2/backup_service.py` | 2351 | ⏳ | `refactor(backend): split backup_service.py into modules` |
| 3 | `api/v2/cas.py` | 1245 | ⏳ | `refactor(backend): split cas.py into modules` |
| 4 | `api/v2/sso.py` | 1843 | ⏳ | `refactor(backend): split sso.py into modules` |
| 5 | `api/v2/system.py` | 1556 | ⏳ | `refactor(backend): split system.py into modules` |
| 6 | `api/v2/settings.py` | 1314 | ⏳ | `refactor(backend): split settings.py into modules` |

**Résultat attendu :** Tous les fichiers API < 800 lignes

---

### Phase 2: Backend Services (Priorité HAUTE) ⬆️
**Objectif :** Découper les services > 900 lignes et corriger dépendances

| # | Fichier | Lignes | Statut | Commit prévu |
|---|--------|--------|--------|---------------|
| 7 | `services/backup_service.py` | 2351 | ⏳ | `refactor(backend): split backup_service.py` |
| 8 | `services/trust_store.py` | 1487 | ⏳ | `refactor(backend): split trust_store.py` |
| 9 | `services/acme/acme_service.py` | 1456 | ⏳ | `refactor(backend): split acme_service.py` |
| 10 | `services/acme/acme_proxy_service.py` | 998 | ⏳ | `refactor(backend): split acme_proxy_service.py` |
| 11 | `services/pdf_report_service.py` | 1298 | ⏳ | `refactor(backend): split pdf_report_service.py` |
| 12 | **Corriger dépendances circulaires** | - | ⏳ | `refactor(backend): fix circular imports services→api` |
| 13 | **Extraire export_service.py** | - | ⏳ | `refactor(backend): create export_service.py` |

**Résultat attendu :** Tous les services < 800 lignes, pas de dépendances circulaires

---

### Phase 3: Frontend (Priorité MOYENNE) ⏸️
**Objectif :** Découper les composants > 1500 lignes

| # | Fichier | Lignes | Statut | Commit prévu |
|---|--------|--------|--------|---------------|
| 14 | `pages/SettingsPage.jsx` | 4833 | ⏳ | `refactor(frontend): split SettingsPage.jsx` |
| 15 | `pages/ACMEPage.jsx` | 3527 | ⏳ | `refactor(frontend): split ACMEPage.jsx` |
| 16 | `pages/DiscoveryPage.jsx` | 1854 | ⏳ | `refactor(frontend): split DiscoveryPage.jsx` |
| 17 | `pages/CAsPage.jsx` | 1693 | ⏳ | `refactor(frontend): split CAsPage.jsx` |
| 18 | `pages/CertificatesPage.jsx` | 1464 | ⏳ | `refactor(frontend): split CertificatesPage.jsx` |

**Résultat attendu :** Tous les composants < 800 lignes

---

### Phase 4: Nettoyage (Priorité BASSE) ⏸️
**Objectif :** Améliorer la qualité du code

| # | Tâche | Statut | Commit prévu |
|---|-------|--------|---------------|
| 19 | Ordonner imports (PEP 8) | ⏳ | `refactor: sort imports in backend/` |
| 20 | Remplacer lazy imports | ⏳ | `refactor: replace lazy imports with top-level` |
| 21 | Ajouter type hints | ⏳ | `refactor: add type hints to services/` |
| 22 | Documenter modules | ⏳ | `docs: add module docstrings` |

---

## 📝 Tâches détaillées

### Tâche 1: Découper `api/v2/certificates.py` (2220l)

**Analyse :**
- 19 routes `@bp.route`
- 20 fonctions `def`
- Logique mélangée : CRUD, export, bulk, CT, compliance

**Découpage proposé :**
```
api/v2/certificates/
├── __init__.py           # Imports + registration
├── crud.py               # list, get, create, delete, update (5 routes)
├── export.py             # export_all, export_one, formats (4 routes)
├── bulk.py               # bulk_delete, bulk_export, bulk_revoke, bulk_renew (4 routes)
├── compliance.py         # compliance_stats (1 route)
├── ct.py                 # submit_to_ct (1 route)
└── stats.py              # get_certificate_stats (1 route)
```

**Dépendances à gérer :**
- `from services.cert_service import CertificateService` → tous les fichiers
- `from models import Certificate, CA, db` → tous les fichiers
- `from websocket.emitters import ...` → crud.py, bulk.py

**Étapes :**
1. Créer le dossier `api/v2/certificates/`
2. Créer `__init__.py` avec Blueprint et imports
3. Déplacer les fonctions par thème
4. Mettre à jour `api/v2/__init__.py` (remplacer `certificates_bp` par les nouveaux blueprints)
5. Tester : `pytest backend/tests/test_certificates.py -x -q`
6. Commiter

---

### Tâche 2: Découper `api/v2/cas.py` (1245l)

**Analyse :**
- 15 routes
- 16 fonctions
- Logique : CRUD, import, export, OCSP

**Découpage proposé :**
```
api/v2/cas/
├── __init__.py
├── crud.py               # list, get, create, delete, update
├── import.py             # import_ca
├── export.py             # export_all, export_one
└── ocsp.py               # OCSP responder management (4 routes)
```

---

### Tâche 3: Découper `services/backup_service.py` (2351l)

**Analyse :**
- 1 classe `BackupService` avec 50 méthodes
- Responsabilités : create, restore, export, cleanup, migration

**Découpage proposé :**
```
services/backup/
├── __init__.py
├── backup_service.py    # Classe principale (délégation)
├── create.py             # create_backup, quick_backup, scheduled_backup
├── restore.py           # restore_backup, validate_backup
├── export.py             # export_backup, export_formats
├── cleanup.py            # cleanup_old, apply_retention
└── migration.py          # migrate_db, check_migration
```

**Stratégie :**
- Garder `BackupService` comme facade
- Extraire les méthodes dans des modules séparés
- `BackupService` appelle les fonctions des sous-modules

---

### Tâche 8: Corriger dépendances circulaires

**Problème :**
```python
# Dans services/acme/acme_service.py
from api.v2.acme_local_domains import find_local_domain_ca
from api.v2.acme_domains import find_provider_for_domain
```

**Solution :**
- Déplacer `find_local_domain_ca` et `find_provider_for_domain` vers `services/acme/`
- Créer `services/acme/domain_helpers.py`
- Mettre à jour les imports dans `api/v2/acme_local_domains.py` et `api/v2/acme_domains.py`

---

### Tâche 9: Extraire export_service.py

**Problème :**
- Logique PKCS12/PFX dupliquée dans `cas.py` et `certificates.py`
- Code similaire pour JKS, P7B

**Solution :**
```python
# services/export_service.py
class ExportService:
    @staticmethod
    def export_pkcs12(cert, key, ca_chain=None, password=None, include_chain=False): ...
    @staticmethod
    def export_pfx(cert, key, ca_chain=None, password=None, include_chain=False): ...
    @staticmethod
    def export_jks(...): ...
    @staticmethod
    def export_p7b(...): ...
```

---

## ✅ Progrès

### Backend API
- [x] certificates.py (2220l) → 6 modules (crud, export, bulk, ct, stats, eku) ✅
- [ ] cas.py (1245l) → 4 modules
- [ ] backup_service.py (2351l) → 1 module (déjà service, à découper)
- [ ] system.py (1556l) → à analyser
- [ ] sso.py (1843l) → à analyser
- [ ] settings.py (1314l) → à analyser

### Backend Services
- [ ] backup_service.py (2351l) → 6 modules
- [ ] trust_store.py (1487l) → à analyser
- [ ] acme_service.py (1456l) → à analyser
- [ ] acme_proxy_service.py (998l) → à analyser
- [ ] pdf_report_service.py (1298l) → à analyser
- [ ] Corriger dépendances circulaires
- [ ] Extraire export_service.py

### Frontend
- [ ] SettingsPage.jsx (4833l)
- [ ] ACMEPage.jsx (3527l)
- [ ] DiscoveryPage.jsx (1854l)
- [ ] CAsPage.jsx (1693l)
- [ ] CertificatesPage.jsx (1464l)

---

## 📅 Historique des commits

| Date | Commit | Description | Statut |
|------|--------|-------------|--------|
| 2026-05-01 | aaae72f1 | docs(refactor): add comprehensive refactoring plan | ✅ |
| 2026-05-01 | 317253e9 | refactor(backend): split certificates.py (2220l) into modular structure | ✅ |

*(À mettre à jour après chaque commit)*

---

## 🔄 Mise à jour du plan

**Règles :**
1. Après chaque commit, mettre à jour :
   - ✅ Statut de la tâche
   - 📅 Historique des commits
   - 📝 Progrès
2. Si une tâche bloque, ajouter une note dans "Problèmes rencontrés"

---

## ⚠️ Problèmes rencontrés

*(À remplir au fur et à mesure)*

---

## 💡 Notes

- **Priorité :** Backend d'abord (plus critique pour maintenabilité)
- **Approche :** Commits atomiques (1 commit = 1 changement logique)
- **Tests :** Toujours lancer `pytest` avant commit
- **Documentation :** Mettre à jour ce fichier après chaque session
