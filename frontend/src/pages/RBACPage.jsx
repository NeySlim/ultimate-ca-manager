/**
 * Roles: no screen of the mockup, drawn as its module list (the users module's frame): the roles
 * with System and Custom chips, then a role's dock, its overview and its permissions, in the group
 * dialog's grid, which a custom role edits as check boxes and a system role only reads. The creation form stays the
 * product's dialog.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Input, FormModal, Select } from '../components/atelier/Form'
import {
  Zone, Icon, Btn, Pill, PageHead, Toolbar, SearchField, ListView, Dock, DockBody, Section, Facts,
  EmptyBlock, NoMatch, LoadError, LoadCause, PermissionGrid, useClientList, useSortParam,
} from '../components/atelier'
import { useNotification } from '../contexts'
import { useModals, usePersistedState } from '../hooks'
import { useDockSelection } from '../components/atelier/useDockParam'
import { rolesService } from '../services'
import {
  groupPermissions, normalizePermissions, ignoredPermissions, appliedPermissions, describePermissions,
} from '../lib/rbacPermissions'

/** A resource's check box: checked when every action is, mixed when only some are. */
function CategoryBox({ label, all, some, disabled, onChange }) {
  const ref = useRef(null)
  useEffect(() => { if (ref.current) ref.current.indeterminate = some && !all }, [some, all])
  return <input ref={ref} type="checkbox" checked={all} disabled={disabled} onChange={onChange} aria-label={label} />
}

const ROLE_SECTIONS = ['overview', 'permissions']
// Named configuration: by name, kept in the address
const BY_NAME = { key: 'name', asc: true }
const SORT_KEYS = ['name', 'description', 'inherits', 'permissions', 'users', 'state']

// The roles the server seeds (their English names), keyed as the account list's role names
const SYSTEM_ROLES = { Administrator: 'admin', Operator: 'operator', Auditor: 'auditor', Viewer: 'viewer' }
const SYSTEM_ROLE_NAMES = { admin: 'users.admin', operator: 'common.operator', auditor: 'common.auditor', viewer: 'common.viewer' }

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
  // The open role and its section live in the URL (`item`, `section`); an unsaved permission edit is held
  const roleDock = useDockSelection(roles, { ready: !loading && !loadError, sections: ROLE_SECTIONS })
  const { section, setSection, select: setSelectedRole } = roleDock
  // Legacy names normalised once, so toggles and display read the same list
  const selectedRole = useMemo(() => (roleDock.selected
    ? { ...roleDock.selected, permissions: normalizePermissions(roleDock.selected.permissions) } : null), [roleDock.selected])
  const selectRole = useCallback((role) => {
    setSelectedRole(role ? { ...role, permissions: normalizePermissions(role.permissions) } : null)
  }, [setSelectedRole])
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

  // The four roles the server seeds are named and described in the language, as the account list names them
  const seeded = (r) => (r?.is_system ? SYSTEM_ROLES[r.name] : null)
  const nameOf = (r) => (seeded(r) ? t(SYSTEM_ROLE_NAMES[seeded(r)]) : r?.name)
  const describe = (r) => (seeded(r) ? t(`rbac.systemRoles.${seeded(r)}`) : r?.description)
  const typeOf = (r) => (r.is_system ? 'system' : 'custom')
  // A type, not a state: a neutral pill, the lock of a system role or the shield of a custom one (the dock's icons)
  const pill = (r) => <Pill label={t(r.is_system ? 'common.system' : 'common.custom')} icon={r.is_system ? 'lock' : 'shield'} />
  const searched = useMemo(() => {
    const q = query.trim().toLowerCase()
    return roles.filter((r) => !q || [r.name, r.description, nameOf(r), describe(r)].some((v) => String(v || '').toLowerCase().includes(q)))
  }, [roles, query, t]) // eslint-disable-line react-hooks/exhaustive-deps -- nameOf and describe follow t
  const rows = searched.filter((r) => !kind || typeOf(r) === kind)
  const views = [
    { id: '', label: t('common.all'), count: searched.length },
    { id: 'system', label: t('common.system'), count: searched.filter((r) => r.is_system).length },
    { id: 'custom', label: t('common.custom'), count: searched.filter((r) => !r.is_system).length },
  ]
  const narrowed = Boolean(query.trim() || kind)
  const create = { label: t('rbac.createRole'), icon: 'plus', onClick: () => openModal('create'), primary: true }
  const parentOf = (r) => (r.inherits_from ? (nameOf(roles.find((x) => x.id === r.inherits_from)) || r.parent_name || `#${r.inherits_from}`) : '—')
  const sortParam = useSortParam(BY_NAME, SORT_KEYS)
  const list = useClientList(rows, {
    sortParam,
    resetKey: `${query}|${kind}`,
    sorts: {
      name: nameOf, description: describe, inherits: (r) => (r.inherits_from ? parentOf(r) : null),
      permissions: (r) => r.all_permissions?.length ?? 0, users: (r) => r.user_count || 0, state: (r) => (r.is_system ? 0 : 1),
    },
  })

  const role = selectedRole
  // Save waits for a change: the open role's permissions against the ones the server listed
  const saved = role ? roles.find((r) => r.id === role.id) : null
  const changed = !!role && !!saved && [...new Set(role.permissions || [])].sort().join() !== [...new Set(saved.permissions || [])].sort().join()
  const direct = role ? appliedPermissions(role.permissions, grantable) : []
  const all = role ? (role.all_permissions || direct) : []
  const ignored = role ? ignoredPermissions(role.permissions, grantable) : []

  const dock = role && (
    <Dock label={t('atelier.detailOf', { name: t('common.rbac') })} tabsLabel={t('atelier.openItem')} activeKey={role.id}
      tabs={[{ key: role.id, title: nameOf(role), icon: role.is_system ? 'lock' : 'shield' }]} onClose={() => setSelectedRole(null)}>
      <DockBody icon={role.is_system ? 'lock' : 'shield'} title={nameOf(role)} badge={pill(role)} section={section} onSection={setSection}
        sectionsLabel={t('atelier.sectionsOf', { name: nameOf(role) })}
        sections={[['overview', t('atelier.overview')], ['permissions', t('common.permissions')]]}
        actions={!role.is_system && <>
          <Btn tone="primary" icon="check" id="rbac-save" write disabled={!changed || undefined} onClick={handleUpdate}>{t('common.saveChanges')}</Btn>
          <Btn tone="danger" icon="block" id="rbac-delete" onClick={() => handleDelete(role)}>{t('common.delete')}</Btn>
        </>}>
        {role.is_system && <p className="notice warn" id="rbac-system"><Icon name="lock" /><span>{t('rbac.systemRoleWarning')}</span></p>}
        {section === 'overview' && (
          <div className="module-detail">
            <Section title={t('atelier.properties')}>
              <Facts items={[
                { label: t('common.type'), value: pill(role) },
                role.inherits_from ? [t('rbac.inheritsFrom'), parentOf(role)] : { label: t('rbac.inheritsFrom'), absent: '—' },
                [t('rbac.columns.users'), t('users.unit', { count: role.user_count || 0 })],
                [t('rbac.columns.permissions'), `${direct.length}/${grantable.length}`],
              ]} />
            </Section>
            <Section title={t('atelier.summary')}>
              <p className="summary">{describe(role) || t('rbac.noDescription')}</p>
            </Section>
          </div>
        )}
        {section === 'permissions' && (
          <div className="module-detail rbac-perms">
            <PermissionGrid label={t('common.permissions')} permissions={grantable}
              lead={{ label: t('common.all'), cell: ({ resource, name }) => (
                <CategoryBox label={t('rbac.allOf', { name })} all={resource.permissions.every((p) => all.includes(p))}
                  some={resource.permissions.some((p) => all.includes(p))} disabled={role.is_system} onChange={() => toggleCategoryPermissions(resource.key)} />
              ) }}
              cell={({ perm, actionName, resourceName }) => {
                const isDirect = direct.includes(perm)
                const isInherited = !isDirect && all.includes(perm)
                return (
                  <>
                    <input type="checkbox" checked={isDirect || isInherited} disabled={role.is_system || isInherited}
                      onChange={() => togglePermission(perm)} aria-label={t('groups.grant', { action: actionName, resource: resourceName })}
                      title={isInherited ? t('rbac.inherited', { name: role.parent_name }) : undefined} />
                    {isInherited && <span className="sr-only">{t('rbac.inherited', { name: role.parent_name })}</span>}
                  </>
                )
              }} />
            {ignored.length > 0 && (
              <Section title={t('rbac.ignoredPermissions')}>
                <p className="small muted perm-intro">{t('rbac.ignoredPermissionsHint')}</p>
                <ul className="perm-list" data-testid="rbac-ignored-permissions">
                  {ignored.map((perm) => <li key={perm}><span className="flag muted"><Icon name="block" />{t('users.notAllowed')}</span><span>{describePermissions(t, [perm])}</span></li>)}
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
          id="rbac-role-name"
          data-autofocus=""
          label={t('rbac.roleName')}
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          placeholder={t('rbac.roleNamePlaceholder')}
        />
        <Input
          id="rbac-role-description"
          label={t('common.description')}
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          placeholder={t('rbac.roleDescription')}
        />
        <Select
          id="rbac-role-inherits"
          full
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
      <ListView label={t('common.rbac')} caption={t('rbac.caption')} icon="shield" list={list} nameSort="name" loading={loading}
        filters={{ views, active: kind, onChange: setKind, label: t('rbac.filterByType') }}
        toolbar={(
          <Toolbar>
            <SearchField id="rbac-search" name="q" label={t('rbac.searchRoles')} placeholder={t('rbac.searchRoles')} value={query} onChange={setQuery} />
          </Toolbar>
        )}
        title={nameOf} status={pill} openedId={role?.id} onOpen={(r) => { setSection('overview'); selectRole(r) }}
        columns={[
          { id: 'description', label: t('common.description'), cell: (r) => describe(r) || '—', kind: 'text', priority: 4, grow: true, muted: true, sort: 'description' },
          { id: 'inherits', label: t('rbac.inheritsFrom'), cell: parentOf, kind: 'text', priority: 3, sort: 'inherits' },
          { id: 'permissions', label: t('rbac.columns.permissions'), labelFull: t('common.permissions'), cell: (r) => r.all_permissions?.length ?? 0, kind: 'number', priority: 3, sort: 'permissions' },
          { id: 'users', label: t('rbac.columns.users'), labelFull: t('common.users'), cell: (r) => r.user_count || 0, kind: 'number', priority: 3, sort: 'users' },
          { status: true, label: t('common.type'), sort: 'state' },
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
        footer={{ range: t('rbac.range', list.counts(roles.length)) }} />
    </Zone>
  )
}
