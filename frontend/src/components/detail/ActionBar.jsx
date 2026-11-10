/**
 * ActionBar: toolbar of labeled buttons rendered from useEntityActions().actions.
 * Only presentation; visibility and handlers come from the hook.
 */
import { cn } from '../../lib/utils'

const BTN = 'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all duration-150'
const TONES = {
  primary: 'text-text-secondary hover:text-accent-primary hover:bg-accent-primary-op10',
  success: 'text-text-secondary hover:text-accent-success hover:bg-accent-success-op10',
  warning: 'text-text-secondary hover:text-status-warning hover:bg-status-warning-op10',
}
const DANGER = 'text-text-tertiary hover:text-status-danger hover:bg-status-danger-op10'

export function ActionBar({ actions = [] }) {
  const shown = actions.filter(a => a.visible && a.inBar !== false)
  const start = shown.filter(a => !a.end)
  const end = shown.filter(a => a.end)

  const render = (a) => {
    const Icon = a.icon
    return (
      <button
        key={a.id}
        type="button"
        onClick={a.onClick}
        disabled={a.disabled}
        className={cn(BTN, a.danger ? DANGER : (TONES[a.tone] || TONES.primary))}
        aria-label={a.iconOnly ? a.label : undefined}
      >
        {Icon && <Icon size={14} weight={a.iconWeight || 'duotone'} />}
        {!a.iconOnly && a.label}
      </button>
    )
  }

  return (
    <div className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 border-b border-border-op40 bg-tertiary-op30">
      {start.map(render)}
      <div className="flex-1" />
      {end.map(render)}
    </div>
  )
}
