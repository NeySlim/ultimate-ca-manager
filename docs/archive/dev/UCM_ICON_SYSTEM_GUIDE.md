# UCM Icon System - Guide d'utilisation

## Architecture

UCM utilise un système d'icônes SVG personnalisé avec gradients thématiques définis dans:
- **Définitions:** `/opt/ucm/frontend/static/data/icons.json`
- **Système:** `/opt/ucm/frontend/static/js/icon-system.js`
- **Version cache:** Actuellement `2.4`

## Syntaxe CORRECTE à utiliser

### ✅ UTILISER PARTOUT: SVG Symbols (méthode native UCM)

```html
<!-- Icône simple -->
<svg class="ucm-icon" width="16" height="16">
    <use href="#icon-trash"/>
</svg>

<!-- Dans un bouton avec style -->
<button class="btn-icon btn-icon-danger" title="Delete">
    <svg class="ucm-icon" width="16" height="16">
        <use href="#icon-trash"/>
    </svg>
</button>

<!-- Tailles disponibles -->
<svg class="ucm-icon" width="20" height="20"><use href="#icon-key"/></svg>
<svg class="ucm-icon" width="24" height="24"><use href="#icon-shield-check"/></svg>
```

### ❌ NE PLUS UTILISER: FontAwesome classes

```html
<!-- ANCIEN STYLE - À NE PLUS UTILISER -->
<i class="fas fa-trash"></i>

<!-- Raisons:
  - Nécessite remplacement JS (moins performant)
  - Incohérent avec le reste de l'application
  - Peut causer des bugs de timing avec HTMX
-->
```

## Classes CSS pour les boutons icônes

```css
/* Bouton icône uniquement */
.btn-icon {
    padding: 0.5rem;
    border-radius: 0.25rem;
    background: transparent;
    border: 1px solid var(--border-color);
}

/* Variantes */
.btn-icon-primary   /* Icône primaire (bleu) */
.btn-icon-danger    /* Icône danger (rouge) */
.btn-icon-success   /* Icône succès (vert) */
.btn-icon-warning   /* Icône warning (orange) */
```

## Icônes disponibles pour v1.7.0

### Authentification / Sécurité
- `#icon-key` - Clés WebAuthn
- `#icon-shield-check` - mTLS, protection
- `#icon-user-check` - Utilisateur authentifié
- `#icon-eye` - Afficher
- `#icon-eye-slash` - Masquer/Désactiver

### Notifications / Communication
- `#icon-bell` - Notifications
- `#icon-envelope` - Email
- `#icon-inbox` - Messages/boîte de réception
- `#icon-server` - Serveur SMTP/mTLS

### Actions
- `#icon-trash` - Supprimer
- `#icon-download` - Télécharger
- `#icon-save` - Sauvegarder
- `#icon-play` - Exécuter/Lancer
- `#icon-plus` - Ajouter

### Interface / Navigation
- `#icon-check` - Validation simple
- `#icon-check-circle` - Validation avec cercle
- `#icon-times` - Fermer/Annuler
- `#icon-circle` - Indicateur de statut
- `#icon-exclamation-circle` - Erreur
- `#icon-warning-triangle` - Avertissement

### Données / Documentation
- `#icon-chart-bar` - Statistiques
- `#icon-book-open` - Documentation
- `#icon-clock` - Temps/Historique

## Migration d'anciennes icônes FontAwesome

### Mapping FontAwesome → UCM Icons

```javascript
'fa-trash'               → '#icon-trash'
'fa-key'                 → '#icon-key'
'fa-shield-alt'          → '#icon-shield-check'
'fa-bell'                → '#icon-bell'
'fa-envelope'            → '#icon-envelope'
'fa-server'              → '#icon-server'
'fa-download'            → '#icon-download'
'fa-save'                → '#icon-save'
'fa-plus'                → '#icon-plus'
'fa-check'               → '#icon-check'
'fa-check-circle'        → '#icon-check-circle'
'fa-times'               → '#icon-times'
'fa-eye'                 → '#icon-eye'
'fa-eye-slash'           → '#icon-eye-slash'
'fa-chart-bar'           → '#icon-chart-bar'
'fa-book-open'           → '#icon-book-open'
'fa-inbox'               → '#icon-inbox'
'fa-play'                → '#icon-play'
'fa-circle'              → '#icon-circle'
'fa-exclamation-circle'  → '#icon-exclamation-circle'
'fa-exclamation-triangle'→ '#icon-warning-triangle'
'fa-clock'               → '#icon-clock'
'fa-user-check'          → '#icon-user-check'
```

## Exemple de conversion

### AVANT (FontAwesome)
```html
<button onclick="deleteItem()" class="btn-danger">
    <i class="fas fa-trash"></i> Delete
</button>
```

### APRÈS (SVG Symbol)
```html
<button onclick="deleteItem()" class="btn-icon btn-icon-danger" title="Delete">
    <svg class="ucm-icon" width="16" height="16">
        <use href="#icon-trash"/>
    </svg>
</button>
```

## Avantages du système SVG Symbols

1. **Performance** - Pas de remplacement DOM JavaScript
2. **Cohérence** - Même système partout dans UCM
3. **Thèmes** - Gradients automatiquement adaptés au thème actif
4. **Fiabilité** - Fonctionne immédiatement, pas de timing HTMX
5. **Cache** - Symboles chargés une seule fois au démarrage

## Ajouter une nouvelle icône

1. Éditer `/opt/ucm/frontend/static/data/icons.json`
2. Ajouter la définition de l'icône avec paths SVG
3. Incrémenter la version dans `icon-system.js` (ligne 19)
4. Ajouter le mapping FontAwesome si nécessaire (ligne 187+)
5. Redéployer et vider le cache navigateur

## Notes importantes

- Les icônes sont injectées dans le DOM au chargement via `<svg id="ucm-gradient-defs">`
- Les symboles sont accessibles via `<use href="#icon-nom"/>`
- Les gradients s'adaptent automatiquement aux 8 thèmes UCM
- Le cache localStorage doit être vidé après mise à jour d'icons.json

## Pages à convertir en priorité

- [x] CA list (déjà en SVG symbols)
- [x] Certificates list (déjà en SVG symbols)
- [ ] WebAuthn page (`/config/webauthn`)
- [ ] mTLS page (`/config/mtls`)
- [ ] Notifications page (`/config/notifications`)

**Date de mise à jour:** 2026-01-07
**Version du système:** 2.4
