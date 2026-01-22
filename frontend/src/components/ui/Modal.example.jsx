import { useState } from 'react';
import { Modal } from './Modal';
import { Button } from './Button';
import { Input } from './Input';
import { Stack } from './LayoutUtils';

/**
 * Exemple d'utilisation du composant Modal
 * Pour les formulaires de création, dialogs de confirmation, etc.
 */

// Exemple 1: Modal de création simple
export function CreateUserModalExample() {
  const [isOpen, setIsOpen] = useState(false);
  const [formData, setFormData] = useState({ name: '', email: '' });

  const handleSubmit = (e) => {
    e.preventDefault();
    console.log('Submit:', formData);
    setIsOpen(false);
  };

  return (
    <>
      <Button onClick={() => setIsOpen(true)}>
        Créer un utilisateur
      </Button>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        title="Créer un nouvel utilisateur"
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
          <Input
            label="Nom"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            required
          />
          <Input
            label="Email"
            type="email"
            value={formData.email}
            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            required
          />
        </Stack>
      </Modal>
    </>
  );
}

// Exemple 2: Modal de confirmation
export function ConfirmDeleteModalExample() {
  const [isOpen, setIsOpen] = useState(false);

  const handleDelete = () => {
    console.log('Delete confirmed');
    setIsOpen(false);
  };

  return (
    <>
      <Button variant="danger" onClick={() => setIsOpen(true)}>
        Supprimer
      </Button>

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
        <p>Êtes-vous sûr de vouloir supprimer cet élément ? Cette action est irréversible.</p>
      </Modal>
    </>
  );
}

// Exemple 3: Modal large pour formulaire complexe
export function CreateCAModalExample() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <Button onClick={() => setIsOpen(true)}>
        Créer une CA
      </Button>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        title="Créer une nouvelle autorité de certification"
        size="lg"
        footer={
          <>
            <Button variant="outline" onClick={() => setIsOpen(false)}>
              Annuler
            </Button>
            <Button>
              Créer la CA
            </Button>
          </>
        }
      >
        <Stack spacing="md">
          <Input label="Nom de la CA" required />
          <Input label="Common Name (CN)" required />
          <Input label="Organization (O)" />
          <Input label="Country (C)" maxLength={2} />
          {/* ... autres champs */}
        </Stack>
      </Modal>
    </>
  );
}

// Exemple 4: Modal sans footer (custom actions dans le body)
export function InfoModalExample() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <Button variant="outline" onClick={() => setIsOpen(true)}>
        Voir info
      </Button>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        title="Informations"
        size="md"
      >
        <Stack spacing="md">
          <p>Ceci est un modal d'information sans footer.</p>
          <Button onClick={() => setIsOpen(false)}>
            Compris
          </Button>
        </Stack>
      </Modal>
    </>
  );
}
