/**
 * Certificates page: slide-over detail of the selected certificate. The panel
 * and the actions are the ones of the detail window.
 */
import { CertificatePanel } from '../../components/detail/CertificatePanel'
import { ActionBar } from '../../components/detail/ActionBar'
import { useEntityActions } from '../../hooks/useEntityActions'

export function CertificateSlideOver({ cert, onChanged, onClose, onMutate, onOpenRelated, onAddToTrustStore }) {
  const { actions, modals } = useEntityActions({ type: 'certificate', entity: cert, onChanged, onClose, onMutate })
  return (
    <>
      <ActionBar actions={actions} />
      <CertificatePanel certificate={cert} onOpenRelated={onOpenRelated} onAddToTrustStore={onAddToTrustStore} />
      {modals}
    </>
  )
}
