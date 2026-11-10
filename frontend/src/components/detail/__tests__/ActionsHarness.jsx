/** Renders the action bar and modals of useEntityActions for a test. */
import { useEntityActions } from '../../../hooks/useEntityActions'
import { ActionBar } from '../ActionBar'

export function ActionsHarness({ type = 'certificate', entity, permissions, ...rest }) {
  const { actions, modals } = useEntityActions({ type, entity, permissions, onClose: () => {}, ...rest })
  return (
    <>
      <ActionBar actions={actions} />
      {modals}
    </>
  )
}
