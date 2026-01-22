# Modal Component

Composant Modal réutilisable basé sur Headless UI Dialog pour les formulaires de création, dialogs de confirmation, et plus.

## Import

```javascript
import { Modal } from '@/components/ui';
// ou
import { Modal } from '@/components/ui/Modal';
```

## Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `isOpen` | `boolean` | - | **Requis.** État d'ouverture du modal |
| `onClose` | `function` | - | **Requis.** Callback appelé lors de la fermeture |
| `title` | `string` | - | **Requis.** Titre affiché dans le header |
| `children` | `ReactNode` | - | Contenu du modal |
| `footer` | `ReactNode` | - | Contenu du footer (généralement des boutons) |
| `size` | `'sm' \| 'md' \| 'lg' \| 'xl'` | `'md'` | Taille du modal |

## Tailles disponibles

- `sm`: 400px - Pour les confirmations simples
- `md`: 600px - Pour les formulaires standards (par défaut)
- `lg`: 800px - Pour les formulaires complexes
- `xl`: 1000px - Pour les formulaires très larges

## Utilisation basique

```javascript
import { useState } from 'react';
import { Modal, Button } from '@/components/ui';

function MyComponent() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <Button onClick={() => setIsOpen(true)}>
        Ouvrir le modal
      </Button>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        title="Mon modal"
        footer={
          <>
            <Button variant="outline" onClick={() => setIsOpen(false)}>
              Annuler
            </Button>
            <Button onClick={() => console.log('Submit')}>
              Valider
            </Button>
          </>
        }
      >
        <p>Contenu du modal</p>
      </Modal>
    </>
  );
}
```

## Exemples d'utilisation

### 1. Formulaire de création

```javascript
<Modal
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  title="Créer un utilisateur"
  size="md"
  footer={
    <>
      <Button variant="outline" onClick={() => setIsOpen(false)}>
        Annuler
      </Button>
      <Button onClick={handleSubmit}>
        Créer
      </Button>
    </>
  }
>
  <Stack spacing="md">
    <Input label="Nom" required />
    <Input label="Email" type="email" required />
  </Stack>
</Modal>
```

### 2. Dialog de confirmation

```javascript
<Modal
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  title="Confirmer la suppression"
  size="sm"
  footer={
    <>
      <Button variant="outline" onClick={() => setIsOpen(false)}>
        Annuler
      </Button>
      <Button variant="danger" onClick={handleDelete}>
        Supprimer
      </Button>
    </>
  }
>
  <p>Êtes-vous sûr de vouloir supprimer cet élément ?</p>
</Modal>
```

### 3. Modal sans footer

```javascript
<Modal
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  title="Informations"
  size="md"
>
  <Stack spacing="md">
    <p>Contenu du modal</p>
    <Button onClick={() => setIsOpen(false)}>
      Fermer
    </Button>
  </Stack>
</Modal>
```

### 4. Formulaire complexe (large)

```javascript
<Modal
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  title="Créer une CA"
  size="lg"
  footer={
    <>
      <Button variant="outline" onClick={() => setIsOpen(false)}>
        Annuler
      </Button>
      <Button onClick={handleSubmit}>
        Créer
      </Button>
    </>
  }
>
  <Stack spacing="md">
    <Input label="Common Name" required />
    <Input label="Organization" />
    <Input label="Country" maxLength={2} />
    {/* Plus de champs... */}
  </Stack>
</Modal>
```

## Fonctionnalités

- ✅ **Headless UI Dialog** - Accessible par défaut (ARIA, focus management)
- ✅ **Transitions animées** - Smooth fade + scale
- ✅ **CSS Modules** - Styles isolés et performants
- ✅ **Fermeture ESC** - Ferme le modal avec la touche Escape
- ✅ **Click backdrop** - Ferme le modal en cliquant sur l'overlay
- ✅ **Focus trap** - Le focus reste dans le modal
- ✅ **Scroll lock** - Empêche le scroll du body
- ✅ **Responsive** - S'adapte aux petits écrans

## Accessibilité

Le composant utilise Headless UI Dialog qui gère automatiquement:
- Les attributs ARIA appropriés
- Le focus trap (focus reste dans le modal)
- Le retour du focus à l'élément déclencheur
- Support de la touche Escape
- Annonce au lecteur d'écran

## Style personnalisé

Le composant utilise des CSS Modules. Pour personnaliser:

```css
/* Dans votre fichier CSS */
.customModal :global(.modal-panel) {
  border-radius: 12px;
}
```

## Notes techniques

- Basé sur `@headlessui/react` v2.2.9+
- Utilise les CSS Variables du design system
- Z-index: 9999
- Overlay: rgba(0, 0, 0, 0.6) avec backdrop blur
- Transitions: 200ms enter, 150ms leave

## Migration depuis l'ancien Modal

```diff
- <Modal opened={isOpen} onClose={onClose} title="Title">
+ <Modal isOpen={isOpen} onClose={onClose} title="Title">
```

Le prop `opened` devient `isOpen` pour plus de cohérence avec Headless UI.
