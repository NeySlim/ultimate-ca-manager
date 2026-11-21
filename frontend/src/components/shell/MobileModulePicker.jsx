/** Phone-width picker, the mockup's select.mobile-nav: the main pages, then the groups of the Modules menu. */
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { isVisible, menuGroupsFor, menuLabelKey, moduleById, MAIN_IDS } from '../../navigation/registry'

export function MobileModulePicker({ can, activeId }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const groups = menuGroupsFor(can)
  const main = MAIN_IDS.map(moduleById).filter(m => m && isVisible(m, can))
  const current = activeId === '' ? 'dashboard' : activeId
  const listed = main.some(m => m.id === current) || groups.some(g => g.modules.some(m => m.id === current))
  return (
    <select
      className="mobile-nav"
      id="mobile-nav"
      aria-label={t('shell.navigate')}
      value={listed ? current : ''}
      onChange={(e) => {
        const mod = moduleById(e.target.value)
        if (mod) navigate(mod.path)
      }}
    >
      {!listed && <option value="" disabled>{t('shell.navigate')}</option>}
      {main.map(m => <option key={m.id} value={m.id}>{t(m.barKey)}</option>)}
      {groups.map(g => (
        <optgroup key={g.id} label={t(g.labelKey)}>
          {g.modules.map(m => <option key={m.id} value={m.id}>{t(menuLabelKey(m))}</option>)}
        </optgroup>
      ))}
    </select>
  )
}
