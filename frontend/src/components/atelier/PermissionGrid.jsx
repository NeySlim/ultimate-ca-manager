/**
 * Permissions as the group dialog grants them: one row per named resource, the read, write and delete
 * columns (then any other action), a cell only where the action is offered. Read only by default
 * (allowed or not, as the mockup's userPermsPanel() flags them); a caller may draw editable cells and
 * a leading column (`lead`: its header and its cell per resource).
 */
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'
import { groupPermissions, permissionActions, ACTION_LABEL_KEYS } from '../../lib/rbacPermissions'

export function PermissionGrid({ permissions = [], granted = () => false, label, labelledBy, lead, cell }) {
  const { t } = useTranslation()
  // A wildcard grants through `granted`; it is no resource of its own
  const offered = permissions.filter((p) => !String(p).includes('*'))
  const resources = groupPermissions(offered)
  const actions = permissionActions(offered)
  const actionName = (a) => (ACTION_LABEL_KEYS[a] ? t(ACTION_LABEL_KEYS[a]) : a)
  const flag = (perm) => (granted(perm)
    ? <span className="flag"><Icon name="check" /><span className="sr-only">{t('users.allowed')}</span></span>
    : <span className="flag muted"><Icon name="block" /><span className="sr-only">{t('users.notAllowed')}</span></span>)
  return (
    <div className="compare-scroll">
      <table className="compare-table group-perms" aria-label={labelledBy ? undefined : label} aria-labelledby={labelledBy}>
        <thead>
          <tr>
            <th scope="col">{t('groups.resource')}</th>
            {lead && <th scope="col">{lead.label}</th>}
            {actions.map((a) => <th key={a} scope="col">{actionName(a)}</th>)}
          </tr>
        </thead>
        <tbody>
          {resources.map((r) => {
            const name = r.labelKey ? t(r.labelKey) : r.label
            return (
              <tr key={r.key}>
                <th scope="row">{name}</th>
                {lead && <td>{lead.cell({ resource: r, name })}</td>}
                {actions.map((a) => {
                  const perm = `${a}:${r.key}`
                  if (!r.permissions.includes(perm)) return <td key={a} />
                  return <td key={a}>{cell ? cell({ perm, action: a, actionName: actionName(a), resource: r, resourceName: name }) : flag(perm)}</td>
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
