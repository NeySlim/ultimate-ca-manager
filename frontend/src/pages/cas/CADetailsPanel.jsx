/**
 * CAs page: slide-over detail of the selected CA. The panel and the actions
 * are the ones of the detail window (CAPanel + useEntityActions).
 */
import { CAPanel } from '../../components/detail/CAPanel'
import { ActionBar } from '../../components/detail/ActionBar'
import { useEntityActions } from '../../hooks/useEntityActions'

export function CADetailsPanel({ ca, canWrite, canDelete, hasPermission, onChanged, onClose, onMutate, t }) {
  const { actions, modals, handler } = useEntityActions({
    type: 'ca',
    entity: ca,
    permissions: { canWrite, canDelete, hasPermission },
    onChanged,
    onClose,
    onMutate,
    t,
  })

  return (
    <>
      <ActionBar actions={actions} />
      <CAPanel
        ca={ca}
        onImportKey={handler('importKey')}
        onCaChanged={onChanged}
        canWriteCas={canWrite('cas')}
        canAttachProfile={canWrite('cas') && !!hasPermission?.('admin:system')}
      />
      {modals}
    </>
  )
}
