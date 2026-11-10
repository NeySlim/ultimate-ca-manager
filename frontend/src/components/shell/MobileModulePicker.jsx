/** Phone-width module picker: one native select over the same visible modules as the mega-menu. */
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { groupsFor, moduleById } from '../../navigation/registry'

export function MobileModulePicker({ can, activeId }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const groups = groupsFor(can)
  const current = activeId === '' ? 'dashboard' : activeId
  const listed = current === 'dashboard' || groups.some(g => g.modules.some(m => m.id === current))
  return (
    <select
      className="shell-mobile-nav"
      aria-label={t('shell.navigate')}
      value={listed ? current : ''}
      onChange={(e) => {
        const mod = moduleById(e.target.value)
        if (mod) navigate(mod.path)
      }}
    >
      {!listed && <option value="" disabled>{t('shell.navigate')}</option>}
      <option value="dashboard">{t('common.dashboard')}</option>
      {groups.map(g => (
        <optgroup key={g.id} label={t(g.labelKey)}>
          {g.modules.map(m => <option key={m.id} value={m.id}>{t(m.labelKey)}</option>)}
        </optgroup>
      ))}
    </select>
  )
}
