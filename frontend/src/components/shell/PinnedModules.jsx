/** Pinned modules, in the stored order, between the fixed pages and the Modules button. */
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { moduleById } from '../../navigation/registry'

export function PinnedModules({ pins, activeId }) {
  const { t } = useTranslation()
  return pins.map(id => {
    const mod = moduleById(id)
    const Icon = mod.icon
    const active = activeId === id
    const label = t(mod.labelKey)
    return (
      <Link
        key={id}
        to={mod.path}
        data-module={id}
        title={label}
        className={`shell-navlink shell-pinned${active ? ' is-active' : ''}`}
        aria-current={active ? 'page' : undefined}
      >
        <Icon size={16} weight={active ? 'fill' : 'regular'} aria-hidden="true" />
        <span className="shell-pin-label">{label}</span>
      </Link>
    )
  })
}
