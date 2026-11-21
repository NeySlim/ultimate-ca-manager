/** Pinned modules, in the stored order, after Activity and before the Modules button (the mockup's pinned links). */
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from '../atelier/Icon'
import { glyphOf, moduleById, menuLabelKey } from '../../navigation/registry'

export function PinnedModules({ pins, activeId }) {
  const { t } = useTranslation()
  return pins.map(id => {
    const mod = moduleById(id)
    const active = activeId === id
    const label = t(menuLabelKey(mod))
    return (
      <Link
        key={id}
        to={mod.path}
        data-module={id}
        className={`pinned-link${active ? ' active' : ''}`}
        aria-current={active ? 'page' : undefined}
        title={label}
      >
        <Icon name={glyphOf(mod)} /><span className="pin-label">{label}</span>
      </Link>
    )
  })
}
