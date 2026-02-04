/**
 * Legacy Help Modal Component - Simple wrapper around Modal
 * @deprecated Use HelpModal from components/ui/HelpModal.jsx with pageKey instead
 */
import { Modal } from './Modal'

export function LegacyHelpModal({ 
  open, 
  onClose, 
  title = 'Help & Information',
  children 
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="md"
    >
      <div className="space-y-4">
        {children}
      </div>
    </Modal>
  )
}

// Re-export new HelpModal as default
export { HelpModal } from './ui/HelpModal'
