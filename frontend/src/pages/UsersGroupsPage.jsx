/**
 * Utilisateurs et rôles: the mockup's users module, a listView() of the accounts (Identifiant,
 * Courriel, Source, Rôle, État, Dernier accès) with its state chips, and the dock of an account
 * (Profil, Permissions, Clés API). What the product has more (search and role filter, groups,
 * single sign-on providers, 2FA, security keys, mTLS certificates, creation, edit and removal)
 * takes the mockup's toolbar, dock actions, record rows and further dock tabs; its forms stay
 * the product's dialogs.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { MemberTransferModal } from '../components'
import {
  Modal as AtelierModal, Input as FieldInput, Select as FieldSelect, ToggleSwitch as FieldToggle, Textarea as FieldTextarea,
  Zone, Icon, Btn, PageHead, Toolbar, SearchField, FilterSelect, ListView, Dock, DockBody, Section, RecordList, RecordRow,
  SimpleOverview, EmptyBlock, NoMatch, AtelierDialog,
} from '../components/atelier'
import { MtlsCertificateDialog } from '../components/mtls/MtlsCertificateDialog'
import { validityDays } from '../components/mtls/validity'
import { usersService, groupsService, rolesService, casService, accountService, ssoService } from '../services'
import { hiddenFromIssuance, listedForIssuance, pickerCas, unlistedPickerCas } from '../lib/caSelection'
import { HiddenCasToggle } from '../components/cas/HiddenCasToggle'
import UserSecurityKeys from '../components/UserSecurityKeys'
import UserApiKeys from '../components/UserApiKeys'
import { useNotification, useAuth } from '../contexts'
import { usePermission, useWebSocket, usePersistedState, useCRUDPage } from '../hooks'
import { downloadBlob } from '../lib/utils'
import { reportSilentFailure } from '../lib/silentFailure'
import { deletedUserWarning, localOnlyRevocationWarning } from '../lib/revocationOutcome'
import UserSecuritySection from './users/UserSecuritySection'
import { UserState, UserProfile, UserPermissions, UserMtls } from './users/UserPanels'
import { ROLE_KEYS, isSso, userName, sourceText } from './users/userFacts'
import { usersCsv } from './users/usersExport'
import { dateOf, dateTimeOf } from './admin/adminDates'
export default function UsersGroupsPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const { user: me } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const { showSuccess, showError, showWarning, showConfirm, showPrompt } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const { muteToasts } = useWebSocket()
  
  // Tab state
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'users')
  
  // groups/roles must be declared before loadFn (loadFn sets them as side effects)
  const [groups, setGroups] = useState([])
  const [roles, setRoles] = useState([])

  // Hook: CRUD state (users sub-section)
  const loadFn = useCallback(async () => {
    const [usersRes, groupsRes, rolesRes] = await Promise.all([
      usersService.getAll(),
      groupsService.getAll(),
      rolesService.getAll().catch(() => ({ data: [] }))
    ])
    setGroups(groupsRes.data || [])
    setRoles(rolesRes.data || [])
    return usersRes.data || []
  }, []) // setGroups/setRoles are stable setState refs
  const {
    items: users, setItems: setUsers,
    loading,
    selectedItem: selectedUser, setSelectedItem: setSelectedUser,
    showModal: showUserModal, setShowModal: setShowUserModal,
    editing: editingUser, setEditing: setEditingUser,
    loadData,
  } = useCRUDPage({ loadFn, loadErrorMsg: t('messages.errors.loadFailed.generic') })

  // Reload when the change was made elsewhere. The loader is read through a
  // ref so the listener never holds a stale closure.
  const loadDataRef = useRef(loadData)
  loadDataRef.current = loadData
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.type === 'user' || e.detail?.type === 'group') loadDataRef.current()
    }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
  }, [])

  // Selection
  const [selectedGroup, setSelectedGroup] = useState(null)

  // Modals
  const [showGroupModal, setShowGroupModal] = useState(false)
  const [showMemberModal, setShowMemberModal] = useState(false)
  const [editingGroup, setEditingGroup] = useState(null)
  const [savingMembers, setSavingMembers] = useState(false)

  // mTLS state (admin user cert management)
  const [userMtlsCerts, setUserMtlsCerts] = useState([])
  const [showMtlsModal, setShowMtlsModal] = useState(false)
  const [mtlsTab, setMtlsTab] = useState('generate')
  const [mtlsCreating, setMtlsCreating] = useState(false)
  const [mtlsResult, setMtlsResult] = useState(null)
  const [mtlsForm, setMtlsForm] = useState({ name: '', validity_days: 365, ca_id: '' })
  const [showHiddenCas, setShowHiddenCas] = useState(false)
  const [mtlsImportForm, setMtlsImportForm] = useState({ name: '', pem: '' })
  const [cas, setCas] = useState([])
  const [availableCerts, setAvailableCerts] = useState([])
  const [availableCertsLoading, setAvailableCertsLoading] = useState(false)
  const [selectedAssignCert, setSelectedAssignCert] = useState(null)

  // SSO linking (#136)
  const [showLinkModal, setShowLinkModal] = useState(false)
  const [linkTarget, setLinkTarget] = useState(null)
  const [linkProviders, setLinkProviders] = useState([])
  const [linkProviderId, setLinkProviderId] = useState('')
  const [linkSaving, setLinkSaving] = useState(false)
  const [linkRemovePassword, setLinkRemovePassword] = useState(false)
  const [linkTenant, setLinkTenant] = useState('')
  // Expected tenant of an attachment to a multi-tenant provider: { user, row, tenant }
  const [tenantEdit, setTenantEdit] = useState(null)
  const [tenantSaving, setTenantSaving] = useState(false)

  // Tab change
  const handleTabChange = (tab) => {
    setActiveTab(tab)
    setSearchParams({ tab })
    setSelectedUser(null)
    setSelectedGroup(null)
    setPage(1)
  }

  // ============= USER ACTIONS =============
  
  const handleCreateUser = async (data) => {
    try {
      muteToasts()
      await usersService.create(data)
      showSuccess(t('messages.success.create.user'))
      setShowUserModal(false)
      setEditingUser(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.createFailed.user'))
    }
  }

  const handleUpdateUser = async (data) => {
    try {
      await usersService.update(editingUser.id, data)
      showSuccess(t('messages.success.update.user'))
      setShowUserModal(false)
      setEditingUser(null)
      loadData()
      if (selectedUser?.id === editingUser.id) {
        setSelectedUser({ ...selectedUser, ...data })
      }
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.user'))
    }
  }

  const handleDeleteUser = async (user) => {
    const confirmed = await showConfirm(t('users.confirmDelete', { name: user.username }), {
      title: t('users.deleteUser'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      muteToasts()
      // Its enrolled certificates are revoked first: one may stay valid, or its ACME CA untold
      const warning = deletedUserWarning(await usersService.delete(user.id), t)
      if (warning) showWarning(warning)
      else showSuccess(t('messages.success.delete.user'))
      if (selectedUser?.id === user.id) setSelectedUser(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.user'))
    }
  }

  const handleToggleUser = async (user) => {
    try {
      await usersService.update(user.id, { active: !user.active })
      showSuccess(t('users.userToggled', { action: user.active ? t('common.disabled') : t('common.enabled') }))
      loadData()
      if (selectedUser?.id === user.id) {
        setSelectedUser({ ...selectedUser, active: !user.active })
      }
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.user'))
    }
  }

  const handleResetPassword = async (user) => {
    const confirmed = await showConfirm(t('users.confirmResetPassword', { name: user.username }), {
      title: t('users.resetPassword'),
      confirmText: t('common.reset')
    })
    if (!confirmed) return
    // The admin chooses the password: the route takes one and never invents one.
    const newPassword = await showPrompt(t('common.newPassword'), {
      title: t('users.resetPassword'),
      type: 'password',
      placeholder: t('common.passwordPlaceholder'),
      confirmText: t('common.reset'),
    })
    if (!newPassword) return
    // The server wants the current password to change your own
    let currentPassword
    if (me && user.id === me.id) {
      currentPassword = await showPrompt(t('common.currentPassword'), {
        title: t('users.resetPassword'),
        type: 'password',
        confirmText: t('common.reset'),
      })
      if (!currentPassword) return
    }
    try {
      await usersService.resetPassword(user.id, newPassword, currentPassword)
      showSuccess(t('messages.success.other.passwordReset'))
    } catch (error) {
      showError(error.message || t('users.resetPasswordFailed'))
    }
  }

  // The 2FA state depends on enforcement and keys: read it back, never guess it
  const refreshSelectedUser = async (id) => {
    try {
      const res = await usersService.getById(id)
      if (res?.data) setSelectedUser(res.data)
    } catch {
      setSelectedUser(null)  // the change applied; only the detail could not be reread
    }
  }

  const handleReset2FA = async (user) => {
    const confirmed = await showConfirm(t('users.confirmReset2fa', { name: user.username }), {
      title: t('users.reset2fa'),
      confirmText: t('common.reset')
    })
    if (!confirmed) return
    try {
      await usersService.reset2FA(user.id)
      showSuccess(t('users.reset2faSuccess'))
      loadData()
      if (selectedUser?.id === user.id) await refreshSelectedUser(user.id)
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.user'))
    }
  }

  const handleToggle2faExempt = async (user) => {
    try {
      const next = !user.totp_exempt
      await usersService.update(user.id, { totp_exempt: next })
      showSuccess(next ? t('users.exempt2faOn') : t('users.exempt2faOff'))
      loadData()
      if (selectedUser?.id === user.id) await refreshSelectedUser(user.id)
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.user'))
    }
  }

  // ============= SSO PROVIDERS =============
  // One row per provider that opens the account; none: a local account
  const ssoRows = (u) => (u && u.sso_identities) || []
  const rowName = (row) => row.provider_name || t('users.sso.deletedProvider')
  // A provider already attached is reset or detached from the account's page, not attached twice
  const attachable = linkProviders.filter(p => !ssoRows(linkTarget).some(r => r.provider_id === p.id))
  const tenantsOf = (p) => (p && Array.isArray(p.oauth2_tenants) ? p.oauth2_tenants : [])
  const linkTenants = tenantsOf(attachable.find(p => String(p.id) === linkProviderId))
  const tenantOptions = (tenants) => tenants.map(tid => ({ value: tid, label: tid }))

  const afterSsoChange = async (id) => {
    await loadData()
    if (selectedUser?.id === id) await refreshSelectedUser(id)
  }

  const handleOpenLinkModal = async (user) => {
    setLinkTarget(user)
    setLinkProviderId('')
    setLinkTenant('')
    setLinkRemovePassword(false)
    setShowLinkModal(true)
    try {
      const res = await ssoService.getProviders()
      setLinkProviders(res.data || res || [])
    } catch (error) {
      setLinkProviders([])
      showError(error.message || t('messages.errors.loadFailed.generic'))
    }
  }

  const handleSubmitLink = async () => {
    if (!linkTarget || !linkProviderId || (linkTenants.length > 0 && !linkTenant)) return
    // Removing the local password leaves the account to its providers alone: confirmed first.
    if (linkRemovePassword) {
      const confirmed = await showConfirm(t('users.sso.confirmRemovePassword', { name: linkTarget.username }),
        { title: t('users.sso.attach'), confirmText: t('users.sso.attach') })
      if (!confirmed) return
    }
    setLinkSaving(true)
    try {
      const body = { provider_id: Number(linkProviderId), remove_password: linkRemovePassword }
      if (linkTenants.length > 0) body.expected_tenant = linkTenant
      await usersService.attachSso(linkTarget.id, body)
      showSuccess(t('users.sso.attachSuccess', { name: linkTarget.username }))
      const id = linkTarget.id
      setShowLinkModal(false)
      setLinkTarget(null)
      await afterSsoChange(id)
    } catch (error) {
      showError(error.message || t('users.sso.attachFailed'))
    } finally {
      setLinkSaving(false)
    }
  }

  const handleDetachSso = async (user, row) => {
    const last = ssoRows(user).length === 1
    const confirmed = await showConfirm(
      t(last ? 'users.sso.confirmDetachLast' : 'users.sso.confirmDetach', { name: user.username, provider: rowName(row) }),
      { title: t('users.sso.detach'), confirmText: t('users.sso.detach') })
    if (!confirmed) return
    try {
      const res = await usersService.detachSso(user.id, row.id)
      showSuccess(res?.message || t('users.sso.detachSuccess', { name: user.username }))
      await afterSsoChange(user.id)
    } catch (error) {
      showError(error.message || t('users.sso.detachFailed'))
    }
  }

  // A multi-tenant provider: the reset (or a pending row) names the tenant that may adopt it,
  // the former identity's by default
  const openTenantEdit = (user, row) => {
    const former = (row.external_id || '').split('/')[0].toLowerCase()
    const tenants = row.provider_tenants || []
    const tenant = tenants.includes(former) ? former : (row.expected_tenant || '')
    setTenantEdit({ user, row, tenant })
  }

  const handleSubmitTenant = async () => {
    if (!tenantEdit || !tenantEdit.tenant) return
    const { user, row, tenant } = tenantEdit
    setTenantSaving(true)
    try {
      await usersService.resetSsoIdentity(user.id, row.id, { expected_tenant: tenant })
      showSuccess(t(row.external_id ? 'users.sso.resetSuccess' : 'users.sso.tenantSet', { name: user.username }))
      setTenantEdit(null)
      await afterSsoChange(user.id)
    } catch (error) {
      showError(error.message || t('users.sso.resetFailed'))
    } finally {
      setTenantSaving(false)
    }
  }

  const handleResetSso = async (user, row) => {
    if ((row.provider_tenants || []).length > 0) {
      openTenantEdit(user, row)
      return
    }
    const confirmed = await showConfirm(
      t('users.sso.confirmReset', { name: user.username, provider: rowName(row) }),
      { title: t('users.sso.resetIdentity'), confirmText: t('users.sso.resetIdentity') })
    if (!confirmed) return
    try {
      await usersService.resetSsoIdentity(user.id, row.id)
      showSuccess(t('users.sso.resetSuccess', { name: user.username }))
      await afterSsoChange(user.id)
    } catch (error) {
      showError(error.message || t('users.sso.resetFailed'))
    }
  }

  // ============= GROUP ACTIONS =============
  
  const handleCreateGroup = async (data) => {
    try {
      muteToasts()
      await groupsService.create(data)
      showSuccess(t('messages.success.create.group'))
      setShowGroupModal(false)
      setEditingGroup(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.createFailed.group'))
    }
  }

  const handleUpdateGroup = async (data) => {
    try {
      await groupsService.update(editingGroup.id, data)
      showSuccess(t('messages.success.update.group'))
      setShowGroupModal(false)
      setEditingGroup(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.group'))
    }
  }

  const handleDeleteGroup = async (group) => {
    const confirmed = await showConfirm(t('groups.confirmDelete', { name: group.name }), {
      title: t('groups.deleteGroup'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      muteToasts()
      await groupsService.delete(group.id)
      showSuccess(t('messages.success.delete.group'))
      if (selectedGroup?.id === group.id) setSelectedGroup(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.group'))
    }
  }

  // Save members from the transfer modal
  const handleSaveMembers = async (newMemberIds) => {
    if (!selectedGroup) return
    
    setSavingMembers(true)
    try {
      const currentIds = new Set((selectedGroup.members || []).map(m => m.id || m.user_id))
      const newIds = new Set(newMemberIds)
      
      // Find members to add
      const toAdd = newMemberIds.filter(id => !currentIds.has(id))
      // Find members to remove
      const toRemove = [...currentIds].filter(id => !newIds.has(id))
      
      // Execute all changes
      await Promise.all([
        ...toAdd.map(userId => groupsService.addMember(selectedGroup.id, userId)),
        ...toRemove.map(userId => groupsService.removeMember(selectedGroup.id, userId))
      ])
      
      showSuccess(t('groups.membersUpdated', { added: toAdd.length, removed: toRemove.length }))
      setShowMemberModal(false)
      loadData()
      
      // Refresh selected group
      const updated = await groupsService.getById(selectedGroup.id)
      setSelectedGroup(updated.data)
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.group'))
    } finally {
      setSavingMembers(false)
    }
  }

  // ============= USER mTLS HANDLERS =============

  const loadUserMtlsCerts = useCallback(async (userId) => {
    try {
      const response = await usersService.getMtlsCertificates(userId)
      setUserMtlsCerts(response.data || [])
    } catch {
      setUserMtlsCerts([])
    }
  }, [])

  const casLoadedRef = useRef(false)
  const loadCAsOnce = useCallback(async () => {
    if (casLoadedRef.current) return
    casLoadedRef.current = true
    try {
      const response = await casService.getAll()
      setCas(response.data?.items || response.data || [])
    } catch (error) { reportSilentFailure('loadCAsOnce', error) }
  }, [])

  // Load mTLS certs when user selected
  useEffect(() => {
    if (selectedUser?.id && canWrite('users')) {
      loadUserMtlsCerts(selectedUser.id)
      loadCAsOnce()
    } else {
      setUserMtlsCerts([])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedUser?.id])

  const handleOpenMtlsModal = () => {
    setMtlsTab('generate')
    setMtlsResult(null)
    setMtlsForm({ name: `${selectedUser?.username || 'user'}@mtls`, validity_days: '365', ca_id: '' })
    setShowHiddenCas(false)
    setMtlsImportForm({ name: '', pem: '' })
    setShowMtlsModal(true)
  }

  const handleCloseMtlsModal = () => {
    setShowMtlsModal(false)
    setMtlsResult(null)
    setSelectedAssignCert(null)
    setAvailableCerts([])
  }

  const handleGenerateUserMtls = async () => {
    if (!selectedUser) return
    setMtlsCreating(true)
    try {
      const response = await usersService.createMtlsCertificate(selectedUser.id, {
        mode: 'generate',
        name: mtlsForm.name || undefined,
        ca_id: mtlsForm.ca_id || undefined,
        validity_days: validityDays(mtlsForm.validity_days),
      })
      setMtlsResult(response.data || {})
      showSuccess(t('users.mtls.generated'))
      loadUserMtlsCerts(selectedUser.id)
    } catch (error) {
      showError(error.message || t('users.mtls.generateFailed'))
    } finally {
      setMtlsCreating(false)
    }
  }

  const handleImportUserMtls = async () => {
    if (!selectedUser || !mtlsImportForm.pem.trim()) return
    setMtlsCreating(true)
    try {
      await usersService.createMtlsCertificate(selectedUser.id, {
        mode: 'import',
        pem: mtlsImportForm.pem,
        name: mtlsImportForm.name,
      })
      showSuccess(t('users.mtls.imported'))
      loadUserMtlsCerts(selectedUser.id)
      handleCloseMtlsModal()
    } catch (error) {
      showError(error.message || t('users.mtls.importFailed'))
    } finally {
      setMtlsCreating(false)
    }
  }

  const handleDeleteUserMtls = async (certId) => {
    if (!selectedUser) return
    const confirmed = await showConfirm(t('users.mtls.deleteConfirm'), {
      title: t('common.deleteCertificate'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      const localOnly = localOnlyRevocationWarning(
        await usersService.deleteMtlsCertificate(selectedUser.id, certId), t)
      if (localOnly) showWarning(localOnly)
      else showSuccess(t('users.mtls.deleted'))
      loadUserMtlsCerts(selectedUser.id)
    } catch (error) {
      showError(error.message || t('users.mtls.deleteFailed'))
    }
  }



  const loadAvailableCerts = async () => {
    setAvailableCertsLoading(true)
    try {
      const response = await accountService.getAvailableMTLSCertificates()
      setAvailableCerts(response.data || [])
    } catch (error) {
      showError(error.message || t('users.mtls.loadAvailableFailed'))
    } finally {
      setAvailableCertsLoading(false)
    }
  }

  const handleAssignUserMtls = async () => {
    if (!selectedUser || !selectedAssignCert) return
    setMtlsCreating(true)
    try {
      await usersService.assignMtlsCertificate({
        cert_id: selectedAssignCert.id,
        user_id: selectedUser.id,
        name: selectedAssignCert.name,
      })
      showSuccess(t('users.mtls.assigned'))
      loadUserMtlsCerts(selectedUser.id)
      handleCloseMtlsModal()
    } catch (error) {
      showError(error.message || t('users.mtls.assignFailed'))
    } finally {
      setMtlsCreating(false)
    }
  }


  // ============= LIST =============

  const [query, setQuery] = useState('')
  const [userView, setUserView] = usePersistedState('ucm-users-state', '')
  const [roleFilter, setRoleFilter] = usePersistedState('ucm-users-role', '')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [section, setSection] = useState('profile')
  const [disabling, setDisabling] = useState(null)

  const roleLabel = (u) => t(ROLE_KEYS[u.role] || 'common.viewer')
  const lastSeen = (u) => (u.last_login ? dateTimeOf(u.last_login, locale) : t('common.never'))
  const groupsTab = activeTab === 'groups'
  const q = query.trim().toLowerCase()
  const matches = (values) => !q || values.some((v) => String(v || '').toLowerCase().includes(q))

  const searchedUsers = useMemo(() => users.filter((u) => (!roleFilter || u.role === roleFilter)
    && matches([u.username, u.email, u.full_name, u.role])), [users, roleFilter, q]) // eslint-disable-line react-hooks/exhaustive-deps
  const USER_VIEWS = { active: (u) => u.active, disabled: (u) => !u.active, sso: isSso }
  const views = [
    { id: '', label: t('common.all'), count: searchedUsers.length },
    { id: 'active', label: t('users.views.active'), count: searchedUsers.filter(USER_VIEWS.active).length },
    { id: 'disabled', label: t('users.views.disabled'), count: searchedUsers.filter(USER_VIEWS.disabled).length },
    { id: 'sso', label: t('users.views.sso'), count: searchedUsers.filter(USER_VIEWS.sso).length },
  ]
  const shownUsers = USER_VIEWS[userView] ? searchedUsers.filter(USER_VIEWS[userView]) : searchedUsers
  const shownGroups = useMemo(() => groups.filter((g) => matches([g.name, g.description])), [groups, q]) // eslint-disable-line react-hooks/exhaustive-deps
  const shown = groupsTab ? shownGroups : shownUsers
  const pages = Math.max(1, Math.ceil(shown.length / perPage))
  const current = Math.min(page, pages)
  const paged = shown.slice((current - 1) * perPage, current * perPage)
  useEffect(() => { setPage(1) }, [q, userView, roleFilter, activeTab])

  // The full list in a file: identity, source, role and state of every account (U07, without the sessions)
  const handleExport = () => {
    downloadBlob(usersCsv(users, {
      head: [t('atelier.name'), t('users.login'), t('users.email'), t('users.source'), t('common.role'), t('atelier.state'), t('users.lastSeen')],
      row: (u) => [userName(u), u.username, u.email, sourceText(t, u), roleLabel(u), u.active ? t('common.active') : t('common.disabled'), u.last_login || ''],
    }), 'users.csv')
  }

  // ============= DETAIL =============

  const self = (u) => Boolean(me && u && u.id === me.id)
  const openUser = (u) => { if (u.id !== selectedUser?.id) setSection('profile'); setSelectedUser(u); setSelectedGroup(null) }
  const openGroup = async (g) => {
    if (g.id !== selectedGroup?.id) setSection('overview')
    setSelectedGroup(g)
    setSelectedUser(null)
    try {
      const res = await groupsService.getById(g.id)
      setSelectedGroup(res.data)
    } catch (error) { reportSilentFailure('openGroup', error) }
  }

  const confirmDisable = async () => {
    const u = disabling
    setDisabling(null)
    if (u) await handleToggleUser(u)
  }

  const sso = {
    attach: handleOpenLinkModal, detach: handleDetachSso, reset: handleResetSso, tenant: openTenantEdit,
  }

  const userActions = (u) => (
    <>
      {canWrite('users') && <Btn icon="settings" write id="user-edit" onClick={() => { setEditingUser(u); setShowUserModal(true) }}>{t('common.edit')}</Btn>}
      {canWrite('users') && <Btn icon="key" write id="user-reset" onClick={() => handleResetPassword(u)}>{`${t('users.resetPassword')}…`}</Btn>}
      {canWrite('users') && !self(u) && (u.active
        ? <Btn tone="danger" icon="block" id="user-disable" onClick={() => setDisabling(u)}>{t('users.disableEllipsis')}</Btn>
        : <Btn icon="check" write id="user-enable" onClick={() => handleToggleUser(u)}>{t('users.activate')}</Btn>)}
      {canDelete('users') && !self(u) && <Btn tone="danger" icon="block" id="user-delete" onClick={() => handleDeleteUser(u)}>{t('common.delete')}</Btn>}
    </>
  )

  const userSections = [
    ['profile', t('users.tabs.profile')], ['permissions', t('users.tabs.permissions')], ['keys', t('users.apiKeys.title')],
    ['security', t('common.security')], ...(canWrite('users') ? [['mtls', t('users.mtls.title')]] : []),
  ]

  const userDock = selectedUser && !groupsTab && (
    <Dock label={t('atelier.detailOf', { name: t('users.title') })} tabsLabel={t('atelier.openItem')} activeKey={selectedUser.id}
      tabs={[{ key: selectedUser.id, title: userName(selectedUser), icon: 'users' }]} onClose={() => setSelectedUser(null)}>
      <DockBody icon="users" title={userName(selectedUser)} badge={<UserState user={selectedUser} />} actions={userActions(selectedUser)}
        sections={userSections} section={userSections.some(([id]) => id === section) ? section : 'profile'} onSection={setSection}
        sectionsLabel={t('atelier.sectionsOf', { name: userName(selectedUser) })}>
        {(section === 'profile' || !userSections.some(([id]) => id === section)) && (
          <UserProfile user={selectedUser} self={self(selectedUser)} canWrite={canWrite('users')} sso={sso} />
        )}
        {section === 'permissions' && <UserPermissions user={selectedUser} />}
        {section === 'keys' && <UserApiKeys user={selectedUser} canRevoke={canWrite('users')} />}
        {section === 'security' && (
          <div className="module-detail">
            <UserSecuritySection user={selectedUser}>
              {canWrite('users') && (
                <div className="copy-url">
                  {selectedUser.totp_enabled && <Btn icon="lock" write onClick={() => handleReset2FA(selectedUser)}>{t('users.reset2fa')}</Btn>}{' '}
                  <Btn icon="lock" write onClick={() => handleToggle2faExempt(selectedUser)}>{selectedUser.totp_exempt ? t('users.require2fa') : t('users.exempt2fa')}</Btn>
                </div>
              )}
            </UserSecuritySection>
            {canWrite('users') && <UserSecurityKeys user={selectedUser} />}
          </div>
        )}
        {section === 'mtls' && canWrite('users') && <UserMtls certs={userMtlsCerts} onAdd={handleOpenMtlsModal} onDelete={handleDeleteUserMtls} />}
      </DockBody>
    </Dock>
  )

  const groupSections = [['overview', t('atelier.overview')], ['members', t('groups.members')], ['permissions', t('groups.permissions')]]
  const groupDock = selectedGroup && groupsTab && (
    <Dock label={t('atelier.detailOf', { name: t('common.groups') })} tabsLabel={t('atelier.openItem')} activeKey={selectedGroup.id}
      tabs={[{ key: selectedGroup.id, title: selectedGroup.name, icon: 'users' }]} onClose={() => setSelectedGroup(null)}>
      <DockBody icon="users" title={selectedGroup.name} sections={groupSections}
        section={groupSections.some(([id]) => id === section) ? section : 'overview'} onSection={setSection}
        sectionsLabel={t('atelier.sectionsOf', { name: selectedGroup.name })}
        actions={<>
          {canWrite('users') && <Btn icon="settings" write id="group-edit" onClick={() => { setEditingGroup(selectedGroup); setShowGroupModal(true) }}>{t('common.edit')}</Btn>}
          {canDelete('users') && <Btn tone="danger" icon="block" id="group-delete" onClick={() => handleDeleteGroup(selectedGroup)}>{t('common.delete')}</Btn>}
        </>}>
        {(section === 'overview' || !groupSections.some(([id]) => id === section)) && (
          <SimpleOverview properties={[
            [t('common.name'), selectedGroup.name],
            [t('common.description'), selectedGroup.description || '—'],
            [t('groups.members'), t('groups.memberCount', { count: selectedGroup.members?.length ?? selectedGroup.member_count ?? 0 })],
            [t('common.created'), dateOf(selectedGroup.created_at, locale) || '—'],
          ]} />
        )}
        {section === 'members' && (
          <div className="module-detail">
            <Section title={t('groups.members')}>
              <RecordList empty={t('groups.noMembers')}>
                {(selectedGroup.members || []).map((m) => (
                  <RecordRow key={m.id || m.user_id || m.username} title={m.username} meta={m.email} />
                ))}
              </RecordList>
              {canWrite('users') && <div className="copy-url"><Btn icon="users" write onClick={() => setShowMemberModal(true)}>{t('groups.manageMembers')}</Btn></div>}
            </Section>
          </div>
        )}
        {section === 'permissions' && (
          Array.isArray(selectedGroup.permissions) && selectedGroup.permissions.length > 0 ? (
            <ul className="perm-list">
              {selectedGroup.permissions.map((p) => <li key={p}><span className="flag"><Icon name="check" />{t('users.allowed')}</span><span className="mono">{p}</span></li>)}
            </ul>
          ) : <p className="muted small">{t('groups.noPermissions')}</p>
        )}
      </DockBody>
    </Dock>
  )

  const createLabel = groupsTab ? t('groups.createGroup') : t('users.createUser')
  const handleOpenCreateModal = () => {
    if (groupsTab) { setEditingGroup(null); setShowGroupModal(true) } else { setEditingUser(null); setShowUserModal(true) }
  }
  const create = canWrite('users') ? { label: createLabel, icon: 'plus', onClick: handleOpenCreateModal, primary: true } : undefined
  const narrowed = Boolean(q || (!groupsTab && (userView || roleFilter)))
  const total = (groupsTab ? groups : users).length
  const footer = shown.length > 10 ? {
    range: t(groupsTab ? 'groups.pageRange' : 'users.pageRange', { start: (current - 1) * perPage + 1, end: Math.min(current * perPage, shown.length), count: shown.length }),
    pagination: { page: current, pages, perPage, sizes: [10, 25, 50, 100], onPage: setPage, onPerPage: (n) => { setPerPage(n); setPage(1) } },
  } : { range: t(groupsTab ? 'groups.range' : 'users.range', { shown: shown.length, count: total }) }
  const empty = narrowed && (groupsTab ? groups : users).length ? (
    <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')}
      onReset={() => { setQuery(''); setUserView(''); setRoleFilter('') }} />
  ) : (
    <EmptyBlock id={groupsTab ? 'groups' : 'users'} icon="users" title={groupsTab ? t('groups.noGroups') : t('users.noUsers')} action={create} />
  )
  const toolbar = (
    <Toolbar>
      <SearchField id="users-search" name="q" label={t(groupsTab ? 'groups.search' : 'users.search')} placeholder={t(groupsTab ? 'groups.search' : 'users.search')}
        value={query} onChange={setQuery} />
      {!groupsTab && (
        <FilterSelect id="users-role" label={t('users.filterByRole')} value={roleFilter} onChange={setRoleFilter}
          options={[{ value: '', label: t('common.allRoles') }, ...Object.entries(ROLE_KEYS).map(([value, key]) => ({ value, label: t(key) }))]} />
      )}
    </Toolbar>
  )

  return (
    <>
      <Zone dock={groupsTab ? groupDock : userDock} after={<>
        {/* User Modal */}
        <AtelierModal
          open={showUserModal}
          onOpenChange={(open) => { setShowUserModal(open); if (!open) setEditingUser(null) }}
          title={editingUser ? t('users.editUser') : t('users.createUser')}
          size="md"
        >
          <UserForm
            user={editingUser}
            isSelf={Boolean(me && editingUser && editingUser.id === me.id)}
            onSubmit={editingUser ? handleUpdateUser : handleCreateUser}
            onCancel={() => { setShowUserModal(false); setEditingUser(null) }}
          />
        </AtelierModal>

        {/* Group Modal */}
        <AtelierModal
          open={showGroupModal}
          onOpenChange={(open) => { setShowGroupModal(open); if (!open) setEditingGroup(null) }}
          title={editingGroup ? t('groups.editGroup') : t('groups.createGroup')}
          size="md"
        >
          <GroupForm
            group={editingGroup}
            onSubmit={editingGroup ? handleUpdateGroup : handleCreateGroup}
            onCancel={() => { setShowGroupModal(false); setEditingGroup(null) }}
          />
        </AtelierModal>
        {/* Attach a provider (#136): the providers the account has keep opening it */}
        {showLinkModal && (
        <AtelierDialog title={t('users.sso.attachTitle', { name: linkTarget?.username || '' })} size="narrow"
          onClose={() => { setShowLinkModal(false); setLinkTarget(null) }} testId="user-sso-attach">
          <form onSubmit={(e) => { e.preventDefault(); handleSubmitLink() }} noValidate>
            <p>{t('users.sso.attachHelp')}</p>
            <div className="form-fields">
              {attachable.length === 0 && linkProviders.length > 0 ? (
                <p className="field full muted small">{t('users.sso.noProviderLeft')}</p>
              ) : (
                <FieldSelect id="sso-attach-provider" data-autofocus full label={t('users.sso.provider')} value={linkProviderId} onChange={(val) => setLinkProviderId(val)}
                  placeholder={t('users.sso.selectProvider')}
                  options={attachable.map(p => ({ value: String(p.id), label: `${p.display_name || p.name} (${(p.provider_type || '').toUpperCase()})` }))} />
              )}
              {linkTenants.length > 0 && (
                <FieldSelect id="sso-attach-tenant" full label={t('users.sso.expectedTenant')} value={linkTenant} onChange={(val) => setLinkTenant(val)}
                  placeholder={t('users.sso.selectTenant')} hint={t('users.sso.expectedTenantHelp')} options={tenantOptions(linkTenants)} />
              )}
              <FieldToggle id="sso-attach-remove-password" checked={linkRemovePassword} onChange={setLinkRemovePassword} label={t('users.sso.removePassword')} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" data-action="close-modal" onClick={() => { setShowLinkModal(false); setLinkTarget(null) }}>{t('common.cancel')}</button>
              <Btn type="submit" tone="primary" icon="link" disabled={!linkProviderId || (linkTenants.length > 0 && !linkTenant) || linkSaving || undefined}>
                {t('users.sso.attach')}
              </Btn>
            </div>
          </form>
        </AtelierDialog>
        )}

        {/* Expected tenant of an attachment to a multi-tenant provider, set on a reset or a pending row */}
        {tenantEdit && (
        <AtelierDialog title={tenantEdit.row.external_id ? t('users.sso.resetIdentity') : t('users.sso.setTenant')} size="narrow"
          onClose={() => setTenantEdit(null)} testId="user-sso-tenant">
          <form onSubmit={(e) => { e.preventDefault(); handleSubmitTenant() }} noValidate>
            {tenantEdit.row.external_id && <p>{t('users.sso.confirmReset', { name: tenantEdit.user.username, provider: rowName(tenantEdit.row) })}</p>}
            <div className="form-fields">
              <FieldSelect id="sso-tenant" data-autofocus full label={t('users.sso.expectedTenant')} value={tenantEdit.tenant} onChange={(val) => setTenantEdit({ ...tenantEdit, tenant: val })}
                placeholder={t('users.sso.selectTenant')} hint={t('users.sso.expectedTenantHelp')} options={tenantOptions(tenantEdit.row.provider_tenants || [])} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" data-action="close-modal" onClick={() => setTenantEdit(null)}>{t('common.cancel')}</button>
              <Btn type="submit" tone={tenantEdit.row.external_id ? 'danger' : 'primary'} disabled={!tenantEdit.tenant || tenantSaving || undefined}>
                {tenantEdit.row.external_id ? t('users.sso.resetIdentity') : t('users.sso.setTenant')}
              </Btn>
            </div>
          </form>
        </AtelierDialog>
        )}

        {/* User mTLS Certificate dialog */}
        {selectedUser && showMtlsModal && (
          <MtlsCertificateDialog title={t('users.mtls.addCert', { username: selectedUser.username })} onClose={handleCloseMtlsModal} busy={mtlsCreating}
            tab={mtlsTab} onTab={(way) => { setMtlsTab(way); if (way === 'assign') loadAvailableCerts() }}
            generateForm={mtlsForm} setGenerateForm={setMtlsForm} namePlaceholder={`${selectedUser.username}@mtls`} onGenerate={handleGenerateUserMtls}
            caPicker={(
              <FieldSelect id="mtls-ca" full label={t('account.mtlsIssuingCA')} value={mtlsForm.ca_id} placeholder={t('account.mtlsDefaultCA')}
                onChange={(val) => setMtlsForm(prev => ({ ...prev, ca_id: val }))}
                options={listedForIssuance(pickerCas(cas, mtlsForm.ca_id), showHiddenCas, mtlsForm.ca_id).map(ca => ({ value: ca.refid || String(ca.id), label: ca.descr || ca.subject || ca.refid }))}
                hint={(unlistedPickerCas(cas, mtlsForm.ca_id) > 0 || hiddenFromIssuance(pickerCas(cas, mtlsForm.ca_id), mtlsForm.ca_id) > 0) && <>
                  {unlistedPickerCas(cas, mtlsForm.ca_id) > 0 && t('cas.notListedForSigning', { count: unlistedPickerCas(cas, mtlsForm.ca_id) })}{' '}
                  <HiddenCasToggle count={hiddenFromIssuance(pickerCas(cas, mtlsForm.ca_id), mtlsForm.ca_id)} shown={showHiddenCas} onToggle={() => setShowHiddenCas(v => !v)} />
                </>} />
            )}
            importForm={mtlsImportForm} setImportForm={setMtlsImportForm} onImport={handleImportUserMtls}
            assign={{ loading: availableCertsLoading, certs: availableCerts, selected: selectedAssignCert, onSelect: setSelectedAssignCert }}
            onAssign={handleAssignUserMtls}
            result={mtlsResult && (
              <>
                <p className="test-result good" role="status"><span>{t('users.mtls.generated')}</span></p>
                <div className="form-fields">
                  <FieldTextarea id="mtls-result-cert" mono readOnly rows={4} label={t('common.certificate')} value={mtlsResult.certificate || ''} />
                  <FieldTextarea id="mtls-result-key" mono readOnly rows={4} label={t('account.privateKey')} value={mtlsResult.private_key || ''} />
                </div>
                <div className="modal-actions">
                  <Btn tone="primary" write={false} onClick={handleCloseMtlsModal}>{t('common.close')}</Btn>
                </div>
              </>
            )} />
        )}
        {disabling && (
        <AtelierDialog title={t('users.disableTitle')} subtitle={userName(disabling)} size="narrow" onClose={() => setDisabling(null)} returnTo="user-disable">
          <div className="notice warn"><Icon name="warning" /><span>{t('users.disableText', { login: disabling.username })}</span></div>
          <div className="modal-actions">
            <button type="button" className="btn" data-action="close-modal" onClick={() => setDisabling(null)}>{t('common.cancel')}</button>
            <Btn tone="danger" id="user-disable-confirm" onClick={confirmDisable}>{t('users.disableConfirm')}</Btn>
          </div>
        </AtelierDialog>
        )}
      </>}>
        <PageHead title={groupsTab ? t('common.groups') : t('users.title')}
          total={groupsTab ? t('groups.unit', { count: groups.length }) : t('users.unit', { count: users.length })}
          intent={groupsTab ? t('groups.intent') : t('users.intent')}
          actions={<>
            <Btn tone="quiet" icon="users" id="users-switch" onClick={() => handleTabChange(groupsTab ? 'users' : 'groups')}>
              {groupsTab ? t('users.accounts') : t('common.groups')}
            </Btn>
            {!groupsTab && <Btn icon="download" data-action="users-export" disabled={!users.length || undefined} onClick={handleExport}>{t('users.exportList')}</Btn>}
            {/* The head's main action is a short verb, as the mockup's « Émettre »: on a phone it sits beside the title on one line */}
            {create && <Btn tone="primary" icon="plus" id="users-new" aria-label={create.label} onClick={create.onClick}>{t('common.create')}</Btn>}
          </>} />
        {groupsTab ? (
          <ListView label={t('common.groups')} caption={t('groups.caption')} icon="users" rows={paged} loading={loading} toolbar={toolbar}
            title={(g) => g.name} status={() => null} openedId={selectedGroup?.id} onOpen={openGroup}
            columns={[
              { id: 'description', label: t('common.description'), cell: (g) => g.description || '—', grow: true, muted: true },
              { id: 'members', label: t('groups.members'), cell: (g) => t('groups.memberCount', { count: g.members?.length ?? g.member_count ?? 0 }) },
            ]}
            empty={empty} footer={footer} />
        ) : (
          <ListView label={t('users.title')} caption={t('users.caption')} icon="users" rows={paged} loading={loading} toolbar={toolbar}
            filters={{ views, active: USER_VIEWS[userView] ? userView : '', onChange: setUserView, label: t('users.filterByState') }}
            title={userName} status={(u) => <UserState user={u} />} openedId={selectedUser?.id} onOpen={openUser}
            columns={[
              { id: 'login', label: t('users.login'), cell: (u) => <span className="mono">{u.username}</span> },
              { id: 'email', label: t('users.email'), cell: (u) => u.email || '—', grow: true, muted: true },
              { id: 'source', label: t('users.source'), cell: (u) => (isSso(u) ? t('users.views.sso') : t('users.authSource.local')) },
              { id: 'role', label: t('common.role'), cell: roleLabel },
              { status: true },
              { id: 'seen', label: t('users.lastSeen'), cell: lastSeen },
            ]}
            empty={empty} footer={footer} />
        )}
      </Zone>

      {/* Member Transfer Modal */}
      {selectedGroup && (
        <MemberTransferModal
          open={showMemberModal}
          onClose={() => setShowMemberModal(false)}
          title={`${t('groups.members')} - ${selectedGroup.name}`}
          allUsers={users}
          currentMembers={selectedGroup.members || []}
          onSave={handleSaveMembers}
          loading={savingMembers}
        />
      )}

    </>
  )
}

// ============= USER FORM =============

function UserForm({ user, isSelf = false, onSubmit, onCancel }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    current_password: '',
    full_name: '',
    role: 'viewer',
    custom_role_id: '',
    active: true
  })
  const [loading, setLoading] = useState(false)
  const [customRoles, setCustomRoles] = useState([])

  useEffect(() => {
    rolesService.listRoles().then(res => {
      setCustomRoles((res.data || []).filter(r => !r.is_system))
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (user) {
      setFormData({
        username: user.username || '',
        email: user.email || '',
        password: '',
        current_password: '',
        full_name: user.full_name || '',
        role: user.role || 'viewer',
        custom_role_id: user.custom_role_id || '',
        active: user.active !== false
      })
    } else {
      setFormData({
        username: '',
        email: '',
        password: '',
        current_password: '',
        full_name: '',
        role: 'viewer',
        custom_role_id: '',
        active: true
      })
    }
  }, [user])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const data = { ...formData }
      if (user && !data.password) delete data.password
      // Only a new password on your own account needs the current one
      if (!user || !data.password || !isSelf) delete data.current_password
      data.custom_role_id = data.custom_role_id ? parseInt(data.custom_role_id) : null
      await onSubmit(data)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-fields">
        <FieldInput label={t('common.username')} value={formData.username} onChange={(e) => setFormData(p => ({ ...p, username: e.target.value }))}
          required disabled={!!user} placeholder={t('users.usernamePlaceholder')} data-autofocus={user ? undefined : true} />
        <FieldInput label={t('common.email')} type="email" value={formData.email} onChange={(e) => setFormData(p => ({ ...p, email: e.target.value }))}
          required placeholder={t('users.emailPlaceholder')} />
        <FieldInput label={t('common.name')} value={formData.full_name} onChange={(e) => setFormData(p => ({ ...p, full_name: e.target.value }))}
          placeholder={t('users.namePlaceholder')} full />
        <FieldInput label={user ? t('common.newPassword') : t('common.password')} type="password" noAutofill value={formData.password}
          onChange={(e) => setFormData(p => ({ ...p, password: e.target.value }))} required={!user} hasExistingValue={!!user} showStrength={!user} />
        {user && isSelf && formData.password && (
          <FieldInput label={t('common.currentPassword')} type="password" noAutofill value={formData.current_password}
            onChange={(e) => setFormData(p => ({ ...p, current_password: e.target.value }))} required />
        )}
        <FieldSelect label={t('common.role')} value={formData.role} onChange={(val) => setFormData(p => ({ ...p, role: val }))}
          options={[
            { value: 'admin', label: t('users.admin') },
            { value: 'operator', label: t('common.operator') },
            { value: 'auditor', label: t('common.auditor') },
            { value: 'viewer', label: t('common.viewer') },
          ]} />
        {customRoles.length > 0 && (
          <FieldSelect label={t('rbac.customRole')} value={formData.custom_role_id} onChange={(val) => setFormData(p => ({ ...p, custom_role_id: val }))}
            options={[{ value: '', label: t('rbac.noCustomRole') }, ...customRoles.map(r => ({ value: String(r.id), label: r.name }))]} />
        )}
        {user && (
          <FieldToggle checked={!!formData.active} onChange={(val) => setFormData(p => ({ ...p, active: val }))}
            label={t('common.status')} description={t('users.activeDescription')} />
        )}
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
        <button type="submit" className="btn primary" disabled={loading || undefined}>{user ? t('common.save') : t('common.create')}</button>
      </div>
    </form>
  )
}

// ============= GROUP FORM =============

function GroupForm({ group, onSubmit, onCancel }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    permissions: []
  })
  const [availablePerms, setAvailablePerms] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    groupsService.getAvailablePermissions()
      .then(res => setAvailablePerms(res.data || res || []))
      .catch(() => setAvailablePerms([]))
  }, [])

  useEffect(() => {
    if (group) {
      setFormData({
        name: group.name || '',
        description: group.description || '',
        permissions: Array.isArray(group.permissions) ? group.permissions : []
      })
    } else {
      setFormData({
        name: '',
        description: '',
        permissions: []
      })
    }
  }, [group])

  const togglePermission = (perm) => {
    setFormData(p => ({
      ...p,
      permissions: p.permissions.includes(perm)
        ? p.permissions.filter(x => x !== perm)
        : [...p.permissions, perm]
    }))
  }

  // Group grantable permissions by their resource (the part after ':')
  const groupedPerms = availablePerms.reduce((acc, perm) => {
    const resource = perm.split(':')[1] || perm
    ;(acc[resource] = acc[resource] || []).push(perm)
    return acc
  }, {})

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await onSubmit(formData)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-fields">
        <FieldInput label={t('groups.groupName')} value={formData.name} onChange={(e) => setFormData(p => ({ ...p, name: e.target.value }))}
          required placeholder={t('groups.namePlaceholder')} data-autofocus />
        <FieldInput label={t('common.description')} value={formData.description} onChange={(e) => setFormData(p => ({ ...p, description: e.target.value }))}
          placeholder={t('groups.descriptionPlaceholder')} />
        {/* One fieldset per resource, its grantable actions as check lines */}
        <div className="field full">
          <span>{t('groups.permissions')}</span>
          <small>{t('groups.permissionsHelp')}</small>
          {Object.keys(groupedPerms).length === 0 ? (
            <small>{t('common.loading')}</small>
          ) : Object.entries(groupedPerms).map(([resource, perms]) => (
            <fieldset key={resource} className="field full">
              <legend>{resource}</legend>
              <div className="choice-grid">
                {perms.map(perm => (
                  <label key={perm} className="checkbox-line">
                    <input type="checkbox" checked={formData.permissions.includes(perm)} onChange={() => togglePermission(perm)} />
                    <span className="mono">{perm}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
        </div>
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
        <button type="submit" className="btn primary" disabled={loading || undefined}>{group ? t('common.save') : t('common.create')}</button>
      </div>
    </form>
  )
}
