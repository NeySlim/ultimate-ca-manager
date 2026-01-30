/**
 * Help Modal Component - Contextual help, stats, and quick actions
 * Opens from FocusPanel help button
 */
import { Modal } from './Modal'
import { Info } from '@phosphor-icons/react'

export function HelpModal({ 
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
