import { useState } from 'react';

/**
 * useModal Hook
 * Simple modal state management
 * 
 * Usage:
 *   const modal = useModal();
 *   
 *   <Button onClick={modal.open}>Open</Button>
 *   <Modal isOpen={modal.isOpen} onClose={modal.close}>...</Modal>
 */
export function useModal(defaultOpen = false) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  const open = () => setIsOpen(true);
  const close = () => setIsOpen(false);
  const toggle = () => setIsOpen(!isOpen);

  return {
    isOpen,
    open,
    close,
    toggle,
  };
}

export default useModal;
