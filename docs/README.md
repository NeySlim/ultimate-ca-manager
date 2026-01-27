# UCM Documentation

Ce dossier contient la documentation technique du projet Ultimate CA Manager.

## Documents Disponibles

### Spécifications API

1. **[UCM-API-SPECIFICATION.md](./UCM-API-SPECIFICATION.md)**
   - Spécification complète du contrat API v2
   - Analyse endpoint par endpoint
   - Structures de réponse standardisées
   - Plan d'implémentation pour corriger les incompatibilités

2. **[API-WIRING-AUDIT.md](./API-WIRING-AUDIT.md)**
   - Audit initial du câblage frontend ↔ backend
   - Liste des bugs critiques trouvés
   - Historique des corrections appliquées
   - Recommandations

## Statut Actuel

**Date:** 2026-01-27  
**Statut:** 🔴 CRITICAL - Incompatibilités frontend/backend majeures

### Problèmes Critiques Identifiés

- **9/9 endpoints** ont des incompatibilités de structure de réponse
- Le backend retourne systématiquement `{data: ..., meta: ...}`
- Le frontend attend diverses structures (`data.certificates`, `data.users`, etc.)
- Pages vides malgré données en DB : CAs, Dashboard
- Dates affichées en "Invalid Date"
- Session ne persistait pas (corrigé)

### Corrections Appliquées

- ✅ Session persistante (AuthContext)
- ✅ CertificatesPage structure de données
- ✅ CAsPage structure de données (partiel)
- ✅ Session timeout étendu à 24h

### Corrections Requises

- ❌ CSRsPage
- ❌ TemplatesPage
- ❌ UsersPage
- ❌ DashboardPage
- ❌ SettingsPage (tous les tabs)
- ❌ CAsPage (tree structure)
- ❌ Mapping des champs de dates

## Plan d'Implémentation

Voir **UCM-API-SPECIFICATION.md** section "Implementation Plan" pour le plan détaillé (90 minutes estimées).

### Phase 1: Pages Critiques (30 min)
- CSRsPage, TemplatesPage, UsersPage, DashboardPage

### Phase 2: Settings Tabs (15 min)
- ACME, SCEP, Database, HTTPS tabs

### Phase 3: Dates (15 min)
- Mapper `valid_from`/`valid_to` → `not_before`/`not_after`

### Phase 4: Tests (30 min)
- Tests manuels de toutes les pages

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

## Utilisation

### Analyse du Contrat API

Un script d'analyse automatique est disponible:

```bash
python3 /tmp/analyze_api_contract.py
```

Ce script:
- Teste tous les endpoints principaux
- Compare structure backend vs attentes frontend
- Génère un rapport JSON détaillé
- Identifie les incompatibilités

### Génération de la Spec

La spécification complète peut être régénérée avec:

```bash
python3 /tmp/analyze_api_contract.py
# Puis générer la spec à partir du rapport JSON
```

## Contribution

Lors de modifications:

1. **Backend:** Respecter la structure `{data, meta}` pour les listes
2. **Frontend:** Toujours utiliser `response.data` pour accéder aux données
3. **Tests:** Vérifier que le contrat est respecté
4. **Documentation:** Mettre à jour ce document et les specs

## Ressources

- **Wiki Backend:** `/root/ultimate-ca-manager.wiki/`
- **Session Copilot:** `/root/.copilot/session-state/434da574-b109-47af-b4e1-c2f9b59f3cb9/`
- **Logs:** `/var/log/ucm/`
- **Database:** `/opt/ucm/data/ucm.db`
