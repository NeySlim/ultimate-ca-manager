/**
 * Roles: no screen of the mockup, drawn as its module list (the users module's frame): the roles
 * with System and Custom chips, then a role's dock, its overview and its permissions, which a
 * custom role edits as check boxes and a system role only reads. The creation form stays the
 * product's dialog.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Input, FormModal, FormSelect } from '../components'
import {
  Zone, Icon, Btn, Pill, PageHead, Toolbar, SearchField, ListView, Dock, DockBody, Section, Props,
  EmptyBlock, NoMatch, LoadError, LoadCause,
} from '../components/atelier'
import { useNotification } from '../contexts'
import { useModals, usePersistedState } from '../hooks'
import { rolesService } from '../services'
import {
  groupPermissions, normalizePermissions, ignoredPermissions, appliedPermissions,
} from '../lib/rbacPermissions'

/** A resource's check box: checked when every action is, mixed when only some are. */
function CategoryBox({ label, all, some, disabled, onChange }) {
  const ref = useRef(null)
  useEffect(() => { if (ref.current) ref.current.indeterminate = some && !all }, [some, all])
  return (
    <label className="checkbox-line">
      <input ref={ref} type="checkbox" checked={all} disabled={disabled} onChange={onChange} />
      <strong>{label}</strong>
    </label>
  )
}

export default function RBACPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { modals, open: openModal, close: closeModal } = useModals(['create'])

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [roles, setRoles] = useState([])
  // What a custom role may grant, as the server enforces it
  const [grantable, setGrantable] = useState([])
  const categories = useMemo(() => groupPermissions(grantable), [grantable])
  const [selectedRole, setSelectedRole] = useState(null)
  const [section, setSection] = useState('overview')
  // Legacy names normalised once, so toggles and display read the same list
  const selectRole = useCallback((role) => {
    setSelectedRole(role ? { ...role, permissions: normalizePermissions(role.permissions) } : null)
  }, [])
  const [kind, setKind] = usePersistedState('ucm-rbac-kind', '')
  const [query, setQuery] = useState('')

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    permissions: [],
    inherits_from: null,
    is_system: false
  })

  // The latest notifier, so a provider that renders a new one each time does not reload the roles
  const notify = useRef(showError)
  notify.current = showError
  const loadRoles = useCallback(async () => {
    try {
      const [res, perms] = await Promise.all([
        rolesService.listRoles(),
        rolesService.listPermissions(),
      ])
      setRoles(res.data || [])
      setGrantable(perms.data || [])
      setLoadError(null)
    } catch (error) {
      setLoadError(error)
      notify.current(t('messages.errors.loadFailed.roles'))
    } finally {
      setLoading(false)
    }
  }, [t])

  // Loaded once on mount; later loads follow a change made here
  useEffect(() => { loadRoles() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleCreate = async () => {
    try {
      await rolesService.createRole(formData)
      showSuccess(t('messages.success.create.role'))
      closeModal('create')
      loadRoles()
      setFormData({ name: '', description: '', permissions: [], inherits_from: null, is_system: false })
    } catch (error) {
      showError(error.message || t('messages.errors.createFailed.role'))
    }
  }

  const handleUpdate = async () => {
    if (!selectedRole || selectedRole.is_system) return
    try {
      await rolesService.updateRole(selectedRole.id, {
        ...selectedRole,
        permissions: normalizePermissions(selectedRole.permissions)
      })
      showSuccess(t('messages.success.update.role'))
      loadRoles()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.role'))
    }
  }

  const handleDelete = async (role) => {
    if (role.is_system) {
      showError(t('messages.confirm.rbac.systemRole'))
      return
    }
    const confirmed = await showConfirm(t('messages.confirm.rbac.deleteRole', { name: role.name }), { variant: 'danger', confirmText: t('common.delete') })
    if (!confirmed) return
    try {
      await rolesService.deleteRole(role.id)
      showSuccess(t('messages.success.delete.role'))
      setSelectedRole(null)
      loadRoles()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.role'))
    }
  }

  const togglePermission = (permission) => {
    if (!selectedRole || selectedRole.is_system) return
    const current = selectedRole.permissions || []
    const updated = current.includes(permission)
      ? current.filter(p => p !== permission)
      : [...current, permission]
    setSelectedRole({ ...selectedRole, permissions: updated })
  }

  const toggleCategoryPermissions = (category) => {
    if (!selectedRole || selectedRole.is_system) return
    const categoryPerms = categories.find(c => c.key === category)?.permissions || []
    const current = selectedRole.permissions || []
    const allSelected = categoryPerms.every(p => current.includes(p))
    const updated = allSelected
      ? current.filter(p => !categoryPerms.includes(p))
      : [...new Set([...current, ...categoryPerms])]
    setSelectedRole({ ...selectedRole, permissions: updated })
  }

  const typeOf = (r) => (r.is_system ? 'system' : 'custom')
  const pill = (r) => <Pill label={t(r.is_system ? 'common.system' : 'common.custom')} tone={r.is_system ? 'muted' : 'good'} />
  const searched = useMemo(() => {
    const q = query.trim().toLowerCase()
    return roles.filter((r) => !q || [r.name, r.description].some((v) => String(v || '').toLowerCase().includes(q)))
  }, [roles, query])
  const rows = searched.filter((r) => !kind || typeOf(r) === kind)
  const views = [
    { id: '', label: t('common.all'), count: searched.length },
    { id: 'system', label: t('common.system'), count: searched.filter((r) => r.is_system).length },
    { id: 'custom', label: t('common.custom'), count: searched.filter((r) => !r.is_system).length },
  ]
  const narrowed = Boolean(query.trim() || kind)
  const create = { label: t('rbac.createRole'), icon: 'plus', onClick: () => openModal('create'), primary: true }
  const parentOf = (r) => (r.inherits_from ? (r.parent_name || `#${r.inherits_from}`) : '—')

  const role = selectedRole
  const direct = role ? appliedPermissions(role.permissions, grantable) : []
  const all = role ? (role.all_permissions || direct) : []
  const ignored = role ? ignoredPermissions(role.permissions, grantable) : []

  const dock = role && (
    <Dock label={t('atelier.detailOf', { name: t('common.rbac') })} tabsLabel={t('atelier.openItem')} activeKey={role.id}
      tabs={[{ key: role.id, title: role.name, icon: role.is_system ? 'lock' : 'shield' }]} onClose={() => setSelectedRole(null)}>
      <DockBody icon={role.is_system ? 'lock' : 'shield'} title={role.name} badge={pill(role)} section={section} onSection={setSection}
        sectionsLabel={t('atelier.sectionsOf', { name: role.name })}
        sections={[['overview', t('atelier.overview')], ['permissions', t('common.permissions')]]}
        actions={!role.is_system && <>
          <Btn tone="primary" icon="check" id="rbac-save" write onClick={handleUpdate}>{t('common.saveChanges')}</Btn>
          <Btn tone="danger" icon="block" id="rbac-delete" onClick={() => handleDelete(role)}>{t('common.delete')}</Btn>
        </>}>
        {role.is_system && <p className="notice warn" id="rbac-system"><Icon name="lock" /><span>{t('rbac.systemRoleWarning')}</span></p>}
        {section === 'overview' && (
          <div className="module-detail">
            <Section title={t('atelier.properties')}>
              <Props items={[
                [t('common.type'), pill(role)],
                [t('rbac.inheritsFrom'), parentOf(role)],
                [t('common.users'), t('rbac.userCount', { count: role.user_count || 0 })],
                [t('common.permissions'), `${direct.length}/${grantable.length}`],
              ]} />
            </Section>
            <Section title={t('atelier.summary')}>
              <p className="summary">{role.description || t('rbac.noDescription')}</p>
            </Section>
          </div>
        )}
        {section === 'permissions' && (
          <div className="module-detail rbac-perms">
            {categories.map((category) => {
              const perms = category.permissions
              return (
                <Section key={category.key} title={category.labelKey ? t(category.labelKey) : category.label}>
                  <CategoryBox label={t('rbac.allOf', { name: category.labelKey ? t(category.labelKey) : category.label })}
                    all={perms.every((p) => all.includes(p))} some={perms.some((p) => all.includes(p))}
                    disabled={role.is_system} onChange={() => toggleCategoryPermissions(category.key)} />
                  <ul className="perm-list">
                    {perms.map((perm) => {
                      const isDirect = direct.includes(perm)
                      const isInherited = !isDirect && all.includes(perm)
                      return (
                        <li key={perm}>
                          <label className="checkbox-line">
                            <input type="checkbox" checked={isDirect || isInherited} disabled={role.is_system || isInherited}
                              onChange={() => togglePermission(perm)} />
                            {perm.split(':')[0]}
                          </label>
                          <span className="mono">{perm}</span>
                          {isInherited && <span className="small muted">{t('rbac.inherited', { name: role.parent_name })}</span>}
                        </li>
                      )
                    })}
                  </ul>
                </Section>
              )
            })}
            {ignored.length > 0 && (
              <Section title={t('rbac.ignoredPermissions')}>
                <p className="small muted perm-intro">{t('rbac.ignoredPermissionsHint')}</p>
                <ul className="perm-list" data-testid="rbac-ignored-permissions">
                  {ignored.map((perm) => <li key={perm}><span className="flag muted"><Icon name="block" />{t('users.notAllowed')}</span><span className="mono">{perm}</span></li>)}
                </ul>
              </Section>
            )}
          </div>
        )}
      </DockBody>
    </Dock>
  )

  return (
    <Zone dock={dock} after={(
      <FormModal
        open={modals.create}
        onClose={() => closeModal('create')}
        title={t('rbac.createCustomRole')}
        onSubmit={handleCreate}
        submitLabel={t('common.create')}
        disabled={!formData.name}
      >
        <Input
          label={t('rbac.roleName')}
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          placeholder={t('rbac.roleNamePlaceholder')}
        />
        <Input
          label={t('common.description')}
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          placeholder={t('rbac.roleDescription')}
        />
        <FormSelect
          label={t('rbac.inheritsFrom')}
          value={formData.inherits_from?.toString() || '__none__'}
          onChange={(value) => setFormData({ ...formData, inherits_from: value && value !== '__none__' ? parseInt(value) : null })}
          options={[
            { value: '__none__', label: t('rbac.inheritNone') },
            ...roles.filter(r => !r.is_system).map(r => ({
              value: r.id.toString(),
              label: r.name
            }))
          ]}
          hint={t('rbac.inheritHint')}
        />
      </FormModal>
    )}>
      <PageHead title={t('common.rbac')} total={t('rbac.unit', { count: roles.length })} intent={t('shell.moduleDesc.rbac')}
        actions={<Btn tone="primary" icon="plus" id="rbac-new" onClick={create.onClick}>{create.label}</Btn>} />
      <ListView label={t('common.rbac')} caption={t('rbac.caption')} icon="shield" rows={rows} loading={loading}
        filters={{ views, active: kind, onChange: setKind, label: t('rbac.filterByType') }}
        toolbar={(
          <Toolbar>
            <SearchField id="rbac-search" name="q" label={t('rbac.searchRoles')} placeholder={t('rbac.searchRoles')} value={query} onChange={setQuery} />
          </Toolbar>
        )}
        title={(r) => r.name} status={pill} openedId={role?.id} onOpen={(r) => { setSection('overview'); selectRole(r) }}
        columns={[
          { id: 'description', label: t('common.description'), cell: (r) => r.description || '—', grow: true, muted: true },
          { id: 'inherits', label: t('rbac.inheritsFrom'), cell: parentOf },
          { id: 'permissions', label: t('common.permissions'), cell: (r) => String(r.all_permissions?.length ?? 0) },
          { id: 'users', label: t('common.users'), cell: (r) => String(r.user_count || 0) },
          { status: true },
        ]}
        error={loadError && (
          <LoadError id="rbac" title={t('messages.errors.loadFailed.roles')} onRetry={() => { setLoading(true); loadRoles() }}
            cause={<LoadCause error={{ status: loadError.status, request: loadError.status && 'GET /api/v2/rbac/roles', message: loadError.message }} />} />
        )}
        empty={narrowed && roles.length ? (
          <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')}
            onReset={() => { setQuery(''); setKind('') }} />
        ) : (
          <EmptyBlock id="rbac" icon="shield" title={t('rbac.noRoles')} text={t('rbac.noRolesDescription')} action={create} />
        )}
        footer={{ range: t('rbac.range', { shown: rows.length, count: roles.length }) }} />
    </Zone>
  )
}
