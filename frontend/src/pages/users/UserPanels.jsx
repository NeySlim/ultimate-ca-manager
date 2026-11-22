/**
 * Panels of the user dock, as the mockup's users module draws them: userProfilePanel() (Identité,
 * Accès), userPermsPanel() (the role, then each permission Autorisé or Non autorisé, read from the
 * effective permissions the server applies, in the group dialog's grid of named resources), and the
 * record rows of the product's own panels (single sign-on providers, mTLS certificates). A group's
 * permissions are read in the same grid.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon, Btn, Pill, Section, Facts, RecordList, RecordRow, PermissionGrid } from '../../components/atelier'
import { rolesService, groupsService } from '../../services'
import { dateOf, dateTimeOf } from '../admin/adminDates'
import { ROLE_KEYS, ssoRowsOf, sourceText, grants } from './userFacts'

// Characters of one unbroken word that still fit the value column of a 360 px panel
const LONG_WORD = 22

export function UserState({ user }) {
  const { t } = useTranslation()
  return user.active ? <Pill label={t('common.active')} tone="good" /> : <Pill label={t('common.disabled')} tone="muted" />
}

export function UserProfile({ user: u, self, canWrite, sso }) {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const role = t(ROLE_KEYS[u.role] || 'common.viewer')
  const created = dateOf(u.created_at, locale)
  return (
    <div className="module-detail">
      <Section title={t('users.identity')}>
        {/* A login or an address too long for the value column goes under its term in a narrow panel */}
        <Facts items={[
          { label: t('users.login'), value: <span className="mono">{u.username}</span>, long: String(u.username || '').length > LONG_WORD },
          u.email ? { label: t('users.email'), value: u.email, long: u.email.length > LONG_WORD } : { label: t('users.email'), absent: '—' },
          [t('users.source'), sourceText(t, u)],
          { label: t('atelier.state'), value: <UserState user={u} /> },
          created ? [t('common.created'), created] : { label: t('common.created'), absent: '—' },
        ]} />
      </Section>
      <Section title={t('users.access')}>
        {/* The role's explanation folds behind its help; a custom role is a second fact of the value */}
        <Facts items={[
          u.custom_role_name
            ? { label: t('common.role'), value: role, sub: t('users.customRoleOf', { name: u.custom_role_name }) }
            : { label: t('common.role'), value: role, help: t(`users.roleDesc.${ROLE_KEYS[u.role] ? u.role : 'viewer'}`) },
          { label: t('users.twoFactor'), state: u.two_factor_enabled ? ['good', t('common.enabled')] : ['muted', t('common.disabled')] },
          u.last_login ? [t('users.lastSeen'), dateTimeOf(u.last_login, locale)] : { label: t('users.lastSeen'), absent: t('common.never') },
        ]} />
        {self && <p className="notice"><Icon name="help" /><span>{t('users.selfNotice')}</span></p>}
      </Section>
      <Section title={t('users.sso.providers')}>
        <RecordList empty={t('users.sso.noProviders')}>
          {ssoRowsOf(u).map((row) => (
            <RecordRow key={row.id} title={<span title={row.orphan_of || undefined}>{row.provider_name || t('users.sso.deletedProvider')}</span>}
              meta={row.state === 'pending' && (row.provider_tenants || []).length > 0
                ? <span className="mono">{row.expected_tenant ? t('users.sso.expectedTenantShort', { tenant: row.expected_tenant }) : t('users.sso.noExpectedTenant')}</span>
                : undefined}
              badge={<Pill label={t(`users.sso.state.${row.state}`)} tone={{ bound: 'good', pending: 'warn', orphan: 'muted' }[row.state]} />}
              action={canWrite && <>
                {row.external_id && <Btn icon="refresh" write onClick={() => sso.reset(u, row)}>{t('users.sso.resetIdentity')}</Btn>}
                {!row.external_id && (row.provider_tenants || []).length > 0 && <Btn write onClick={() => sso.tenant(u, row)}>{t('users.sso.setTenant')}</Btn>}
                <Btn icon="block" write onClick={() => sso.detach(u, row)}>{t('users.sso.detach')}</Btn>
              </>} />
          ))}
        </RecordList>
        {canWrite && <div className="copy-url"><Btn icon="link" write onClick={() => sso.attach(u)}>{t('users.sso.attach')}</Btn></div>}
      </Section>
    </div>
  )
}

export function UserPermissions({ user }) {
  const { t } = useTranslation()
  const [state, setState] = useState({ loading: true })
  useEffect(() => {
    let live = true
    setState({ loading: true })
    Promise.all([rolesService.getEffectivePermissions(user.id), rolesService.listPermissions().catch(() => ({ data: [] }))])
      .then(([eff, all]) => { if (live) setState({ effective: eff.data || [], catalog: all.data || [] }) })
      .catch((error) => { if (live) setState({ error }) })
    return () => { live = false }
  }, [user.id])
  const role = t(ROLE_KEYS[user.role] || 'common.viewer')
  if (state.loading) return <p className="small muted perm-intro" aria-busy="true">{t('users.permsLoading')}</p>
  if (state.error) return <p className="field-error" role="alert"><Icon name="warning" /><span>{t('users.permsFailed')}</span></p>
  return (
    <>
      <p className="small muted perm-intro">{t('users.permsIntro', { role: user.custom_role_name ? `${role}, ${user.custom_role_name}` : role })}</p>
      <PermissionGrid label={t('users.tabs.permissions')} permissions={[...new Set([...state.catalog, ...state.effective])]}
        granted={(p) => grants(state.effective, p)} />
    </>
  )
}

/** A group's permissions: what the server lets a group grant, and what this one holds beyond it. */
export function GroupPermissions({ group }) {
  const { t } = useTranslation()
  const [catalog, setCatalog] = useState([])
  useEffect(() => {
    let live = true
    groupsService.getAvailablePermissions()
      .then((res) => { if (live) setCatalog(res.data || res || []) })
      .catch(() => { if (live) setCatalog([]) })
    return () => { live = false }
  }, [])
  const held = Array.isArray(group.permissions) ? group.permissions : []
  if (held.length === 0) return <p className="muted small">{t('groups.noPermissions')}</p>
  return <PermissionGrid label={t('groups.permissions')} permissions={[...new Set([...catalog, ...held])]} granted={(p) => held.includes(p)} />
}

export function UserMtls({ certs, onAdd, onDelete }) {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  return (
    <div className="module-detail">
      <Section title={t('users.mtls.title')}>
        <p className="small muted perm-intro">{t('users.mtls.description')}</p>
        <RecordList empty={t('users.mtls.noCerts')}>
          {certs.map((cert) => (
            <RecordRow key={cert.id} title={cert.name || cert.cert_subject} meta={`${t('common.expires')} ${dateOf(cert.valid_until, locale)}`}
              badge={<Pill label={cert.enabled ? t('common.active') : t('common.disabled')} tone={cert.enabled ? 'good' : 'warn'} />}
              action={<Btn icon="block" write aria-label={t('common.delete')} onClick={() => onDelete(cert.id)}>{t('common.delete')}</Btn>} />
          ))}
        </RecordList>
        <div className="copy-url"><Btn icon="plus" write onClick={onAdd}>{t('common.add')}</Btn></div>
      </Section>
    </div>
  )
}
