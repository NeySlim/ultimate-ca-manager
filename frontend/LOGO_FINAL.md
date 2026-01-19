# UCM Logo - Certificate Chain ⛓️

## Logo Final Choisi

Le logo **Certificate Chain** a été sélectionné pour représenter Ultimate Certificate Manager.

### Symbolisme

- **3 maillons** : Représentent la chaîne de certificats (Root CA → Intermediate CA → End-entity)
- **Ondulation** : Connexion et flux sécurisé entre les certificats
- **Gradient subtil** : Moderne et professionnel
- **Formes arrondies** : Approche accessible tout en restant technique

## Fichiers Créés

### Assets SVG
```
/frontend/assets/
├── logo-chain.svg          (60×40) - Logo principal horizontal
├── logo-chain-icon.svg     (48×48) - Icône carrée pour apps
└── favicon.svg             (32×32) - Favicon
```

### Démonstration Complète
```
/frontend/demos/logo-chain-complete.html
```

Contient:
- Toutes les variations (horizontal, vertical, compact)
- Versions avec/sans texte
- Tailles multiples (SM, MD, LG, XL)
- Favicon preview (16px → 256px)
- Exemples en contexte (navbar, login)
- Export SVG/PNG
- 5 thèmes de couleurs

## Utilisation

### En Production
```
https://netsuit.lan.pew.pet:8443/assets/logo-chain.svg
https://netsuit.lan.pew.pet:8443/assets/logo-chain-icon.svg
https://netsuit.lan.pew.pet:8443/assets/favicon.svg
```

### Démo Interactive
```
https://netsuit.lan.pew.pet:8443/logo-chain-complete.html
```

## Variations Principales

### 1. Logo Horizontal (Navbar, Header)
```html
<div class="chain chain-horizontal">
    <div class="chain-link"></div>
    <div class="chain-link"></div>
    <div class="chain-link"></div>
</div>
<div class="logo-text">UCM</div>
```

### 2. Logo Vertical (Login, Splash)
```html
<div class="chain chain-vertical">
    <div class="chain-link"></div>
    <div class="chain-link"></div>
    <div class="chain-link"></div>
</div>
<div class="logo-ucm">UCM</div>
```

### 3. Compact (Mobile, Navbar)
```html
<div class="chain chain-horizontal chain-compact">
    <div class="chain-link"></div>
    <div class="chain-link"></div>
    <div class="chain-link"></div>
</div>
```

## CSS de Base

```css
.chain {
    display: flex;
    gap: 4px;
}

.chain-link {
    width: 16px;
    height: 24px;
    border: 3px solid;
    border-image: linear-gradient(135deg, #5a8fc7, #7aa5d9) 1;
    border-radius: 8px;
}

.chain-link:nth-child(2) {
    transform: translateY(8px);
}

.chain-link:nth-child(3) {
    transform: translateY(-4px);
}
```

## Thèmes de Couleur

### Blue Sky (Défaut)
```css
--accent-gradient-start: #5a8fc7;
--accent-gradient-end: #7aa5d9;
```

### Purple Dream
```css
--accent-gradient-start: #9985c7;
--accent-gradient-end: #b5a3d9;
```

### Mint Fresh
```css
--accent-gradient-start: #5eb89b;
--accent-gradient-end: #7bc9af;
```

### Amber Warm
```css
--accent-gradient-start: #c99652;
--accent-gradient-end: #d9ac73;
```

### Mokka
```css
--accent-gradient-start: #b8926d;
--accent-gradient-end: #c9a687;
```

## Intégration au Design System

Le logo est cohérent avec:
- ✅ Police: Inter
- ✅ Gradients subtils (135deg)
- ✅ Border-radius: 3px (formes carrées)
- ✅ Approche compacte et dense
- ✅ Variables CSS pour thèmes

## Prochaines Étapes

1. [x] Créer page de démo complète
2. [x] Générer assets SVG
3. [ ] Intégrer au design-system.html
4. [ ] Utiliser dans login-design.html
5. [ ] Créer favicon.ico multi-résolution
6. [ ] Générer PNG (256×256, 512×512, 1024×1024)
7. [ ] Créer Apple Touch Icon
8. [ ] Ajouter au README principal

## Commits Git

- `d430c90` - UCM Certificate Chain logo - Complete package
- `8e93b2d` - Add SVG logo assets for Certificate Chain

## Notes

Le logo est créé en **pur CSS**, ce qui permet:
- Adaptation dynamique aux thèmes
- Pas de fichiers images lourds pour les variations
- Facilité d'intégration dans les composants React
- Support natif du responsive
