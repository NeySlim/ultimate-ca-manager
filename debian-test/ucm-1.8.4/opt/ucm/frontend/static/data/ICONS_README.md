# UCM Dynamic Icon System

## Overview
Le système d'icônes UCM fournit des icônes SVG stylisées avec des gradients qui s'adaptent automatiquement à chaque thème actif.

## Caractéristiques

### ✨ Gradients Dynamiques
- Chaque icône utilise des gradients définis par le thème actif
- Les couleurs changent automatiquement lors du changement de thème
- Gradients définis pour: primary, accent, success, warning, danger, info

### 🎨 Thèmes Supportés
- **Sentinel Light/Dark** - Bleu corporatif
- **Amber Light/Dark** - Orange chaleureux
- **Nebula Light/Dark** - Bleu datacenter
- **Blossom Light/Dark** - Violet/rose élégant

### 🚀 Performance
- Cache des SVG générés
- Injection unique des définitions de gradients
- Chargement asynchrone du JSON

## Utilisation

### Dans le HTML
```html
<!-- Les icônes FontAwesome sont automatiquement remplacées -->
<i class="fas fa-lock"></i>
```

### En JavaScript
```javascript
// Obtenir un SVG icon
const svg = window.ucmIcons.getIcon('certificate', 'my-class', 24);

// Injecter dans le DOM
element.innerHTML = svg;

// Remplacer toutes les icônes FontAwesome
window.ucmIcons.replaceFontAwesomeIcons();
```

### Ajouter une Nouvelle Icône

1. **Éditer `/opt/ucm/frontend/static/data/icons.json`:**
```json
{
  "icons": {
    "mon-icone": {
      "viewBox": "0 0 24 24",
      "paths": [
        {
          "d": "M12 2L2 7v10c0 5.55...",
          "gradient": "primary",
          "opacity": 0.2
        }
      ]
    }
  }
}
```

2. **Utiliser l'icône:**
```javascript
const svg = window.ucmIcons.getIcon('mon-icone', '', 32);
```

### Ajouter un Thème

1. **Créer le fichier CSS du thème**
```css
/* /opt/ucm/frontend/static/css/themes/mytheme-dark.css */
:root {
    --primary-color: #hexcolor;
    ...
}
```

2. **Ajouter les gradients dans icons.json:**
```json
{
  "gradients": {
    "mytheme-dark": {
      "primary": ["#color1", "#color2"],
      "accent": ["#color3", "#color4"],
      ...
    }
  }
}
```

3. **Ajouter au menu de sélection:**
```html
<a href="#" onclick="setTheme('mytheme-dark')">Mon Thème Dark</a>
```

## API JavaScript

### `ucmIcons.init()`
Initialise le système d'icônes.
```javascript
await window.ucmIcons.init();
```

### `ucmIcons.getIcon(name, className, size)`
Retourne un SVG en string.
```javascript
const svg = window.ucmIcons.getIcon('dashboard', 'my-icon', 32);
// <svg class="ucm-icon my-icon" width="32" height="32"...
```

### `ucmIcons.updateTheme(themeName)`
Met à jour les gradients pour un nouveau thème.
```javascript
window.ucmIcons.updateTheme('blossom-dark');
```

### `ucmIcons.replaceFontAwesomeIcons()`
Remplace toutes les icônes FontAwesome par des SVG dynamiques.
```javascript
window.ucmIcons.replaceFontAwesomeIcons();
```

## Structure des Fichiers

```
/opt/ucm/frontend/static/
├── data/
│   └── icons.json              # Définitions icônes + gradients
├── js/
│   ├── icon-system.js          # Système d'icônes
│   └── theme-switcher.js       # Gestion des thèmes
└── css/
    └── themes/
        ├── sentinel-light.css
        ├── sentinel-dark.css
        ├── amber-light.css
        ├── amber-dark.css
        ├── nebula-light.css
        ├── nebula-dark.css
        ├── blossom-light.css
        └── blossom-dark.css
```

## Icônes Disponibles

| Nom | Description | Gradient |
|-----|-------------|----------|
| `dashboard` | Tableau de bord | primary |
| `certificate-authority` | Autorité de certification | primary + accent |
| `certificate` | Certificat | primary + accent |
| `scep` | SCEP protocol | primary |
| `settings` | Paramètres | primary + accent |
| `user` | Utilisateur | primary |
| `refresh` | Rafraîchir (animé) | primary |
| `theme-palette` | Sélecteur de thème | primary + accent |
| `moon` | Mode sombre | primary |
| `sun` | Mode clair | warning |
| `logout` | Déconnexion | danger |
| `check-circle` | Validation | success |
| `warning-triangle` | Avertissement | warning |

## Animations

### Rotation
Les icônes avec `"animate": { "rotate": true }` tournent automatiquement:
```json
{
  "refresh": {
    ...
    "animate": {
      "rotate": true
    }
  }
}
```

CSS auto-généré:
```css
.ucm-icon-rotate {
    animation: ucm-rotate 2s linear infinite;
}
```

## Debug

### Console Logs
```javascript
// Vérifier l'initialisation
✅ Icon system initialized with theme: blossom-dark

// Vérifier les changements de thème
🎨 Icon system updated to theme: sentinel-light
```

### Vérifier les Gradients
```javascript
// Inspecter les gradients injectés
document.getElementById('ucm-gradient-defs');
```

### Cache
```javascript
// Vider le cache d'icônes
window.ucmIcons.svgCache.clear();
```

## Notes

- Les gradients sont injectés dans un `<svg>` caché en début de `<body>`
- Le cache est vidé automatiquement lors du changement de thème
- Compatible avec tous les navigateurs modernes (pas IE11)
- Les icônes s'adaptent à la taille de leur `font-size` parent

## Exemple Complet

```html
<!DOCTYPE html>
<html>
<head>
    <link id="theme-css" rel="stylesheet" href="/static/css/themes/blossom-dark.css">
</head>
<body>
    <div class="card">
        <i class="fas fa-certificate"></i> Certificate
    </div>

    <script src="/static/js/icon-system.js"></script>
    <script>
        // Attend l'initialisation
        window.addEventListener('load', () => {
            // Les icônes FA sont maintenant des SVG avec gradients
            console.log('Icons ready!');
        });
    </script>
</body>
</html>
```

## Dépannage

**Problème:** Les icônes n'apparaissent pas
- Vérifier que `icon-system.js` est chargé avant `theme-switcher.js`
- Vérifier la console pour les erreurs de fetch de `icons.json`

**Problème:** Les gradients ne changent pas
- S'assurer que `window.ucmIcons.updateTheme()` est appelé
- Vérifier que le thème existe dans `icons.json`

**Problème:** Performance lente
- Le cache devrait gérer ça, vérifier `svgCache.size`
- Réduire le nombre d'icônes si nécessaire
