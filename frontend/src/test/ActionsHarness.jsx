/** Renders the actions of useEntityActions as plain buttons, and their modals, for a test of the hook. */
import { useEntityActions } from '../hooks/useEntityActions'

export function ActionsHarness({ type = 'certificate', entity, permissions, ...rest }) {
  const { actions, modals } = useEntityActions({ type, entity, permissions, onClose: () => {}, ...rest })
  return (
    <>
      {actions.filter((a) => a.visible && a.inBar !== false).map((a) => (
        <button key={a.id} type="button" onClick={a.onClick} disabled={a.disabled} aria-label={a.iconOnly ? a.label : undefined}>
          {!a.iconOnly && a.label}
        </button>
      ))}
      {modals}
    </>
  )
}
