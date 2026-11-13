import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { ArrowsClockwise, FloppyDisk, CheckCircle, WarningCircle, ListChecks, Key } from '@phosphor-icons/react'
import { Badge, Button, Input, Select, Textarea, HelpCard } from '../../components'
import { FileUpload } from '../../components/FileUpload'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { windowsProfilesService, adConnectorsService, templatesService } from '../../services'
import { useNotification } from '../../contexts'
import { pickerCas, unlistedPickerCas } from '../../lib/caSelection'
import {
  realmProblem, realmOfBaseDn, groupEntriesByRealm, foreignRealms, profileChecklist,
} from '../../lib/windowsProfile'

const EMPTY = {
  name: '', realm: '', enabled: true, connector_id: null, issuing_ca_refid: '', policy_ca_refid: '',
  validity_days: 365, allowed_ad_group: '', pinned_subject_fields: '', template_ids: [],
  xcep_username: '', wstep_username: '', is_default: false,
}

function ChecklistRow({ ok, label, action, onAction }) {
  return (
    <div className="flex items-center justify-between gap-2 py-1">
      <div className="flex items-center gap-2">
        {ok
          ? <CheckCircle size={16} weight="fill" className="text-status-success shrink-0" />
          : <WarningCircle size={16} weight="fill" className="text-status-warning shrink-0" />}
        <span className="text-sm text-text-primary">{label}</span>
      </div>
      {!ok && action && <Button type="button" size="sm" variant="ghost" onClick={onAction}>{action}</Button>}
    </div>
  )
}

/** The keytab entries of a profile, grouped by realm, the realm that is not the profile's flagged. */
export function KeytabEntries({ entries, profileRealm }) {
  const { t } = useTranslation()
  const groups = groupEntriesByRealm(entries)
  const foreign = new Set(foreignRealms(entries, profileRealm))
  if (!groups.length) return <p className="text-xs text-text-tertiary">{t('xcepWstep.keytabNoEntries')}</p>
  return (
    <div className="space-y-2" data-testid="keytab-entries">
      {groups.map(({ realm, entries: list }) => (
        <div key={realm}>
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-medium text-text-primary">{realm}</span>
            <Badge variant={foreign.has(realm) ? 'danger' : 'success'} size="sm">
              {foreign.has(realm) ? t('xcepWstep.keytabRealmDiffers', { realm: profileRealm || '-' }) : t('xcepWstep.keytabRealmMatches')}
            </Badge>
          </div>
          <ul className="pl-4 text-xs text-text-secondary">
            {list.map((entry, index) => (
              <li key={`${entry.principal}-${entry.kvno}-${entry.enctype}-${index}`} className="font-mono break-all">
                {entry.principal} (kvno {entry.kvno}, etype {entry.enctype})
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

export default function WindowsProfileEditor({ profile, cas, canWrite, canUploadKeytab, onSaved, onCancel }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { showSuccess, showError } = useNotification()
  const isNew = !profile?.id
  const [detail, setDetail] = useState(null)
  const [form, setForm] = useState({ ...EMPTY })
  const [connectors, setConnectors] = useState([])
  const [templates, setTemplates] = useState([])
  const [saving, setSaving] = useState(false)
  const [keytabFile, setKeytabFile] = useState(null)
  const [keytabPreview, setKeytabPreview] = useState(null)
  const [touched, setTouched] = useState(false)
  // Offered only while the server says no profile is the default; unknown counts as one existing
  const [noDefault, setNoDefault] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const [conn, tpl, settings] = await Promise.all([
        adConnectorsService.list().catch(() => ({ data: [] })),
        templatesService.getAll().catch(() => ({ data: [] })),
        windowsProfilesService.getSettings().catch(() => null),
      ])
      if (cancelled) return
      setConnectors(conn.data || [])
      setTemplates(tpl.data || [])
      setNoDefault(Boolean(settings?.data) && settings.data.default_profile === null)
      if (!isNew) {
        try {
          const response = await windowsProfilesService.get(profile.id)
          if (cancelled) return
          setDetail(response.data)
          const p = response.data
          setForm({
            name: p.name, realm: p.realm || '', enabled: p.enabled, connector_id: p.connector_id,
            issuing_ca_refid: p.issuing_ca_refid || '', policy_ca_refid: p.policy_ca_refid || '',
            validity_days: p.validity_days || 365, allowed_ad_group: p.allowed_ad_group || '',
            pinned_subject_fields: p.pinned_subject_fields || '', template_ids: p.template_ids || [],
            xcep_username: p.xcep_username || '', wstep_username: p.wstep_username || '',
            is_default: Boolean(p.is_default),
          })
        } catch (error) {
          showError(error.message || t('messages.errors.loadFailed.generic'))
        }
      }
    })()
    return () => { cancelled = true }
  }, [isNew, profile?.id, showError, t])

  const update = (field) => (value) => setForm(prev => ({ ...prev, [field]: value }))
  const offerDefault = noDefault && !detail?.is_default
  // The shared accounts belong to the default profile, including the one designated by this save
  const isDefault = Boolean(detail?.is_default || (offerDefault && form.is_default))
  const problemKey = realmProblem(form.realm)
  // A new profile may be saved without a realm only if one is read from its keytab later: the API decides
  const realmError = touched && form.realm.trim() !== '' && problemKey ? t(problemKey) : undefined

  const connector = connectors.find(c => c.id === form.connector_id)
  const connectorRealm = connector ? (connector.realm || realmOfBaseDn(connector.base_dn)) : null
  const realmMismatch = Boolean(connectorRealm && form.realm && connectorRealm !== form.realm.trim())

  const caOptions = pickerCas(cas, form.issuing_ca_refid, form.policy_ca_refid)
    .map(ca => ({ value: ca.refid, label: ca.descr || ca.common_name }))
  const unlisted = unlistedPickerCas(cas, form.issuing_ca_refid, form.policy_ca_refid)
  const caHelp = unlisted > 0 ? t('cas.notListedForSigning', { count: unlisted }) : undefined

  const autoenrollTemplates = useMemo(
    () => templates.filter(tpl => tpl.autoenroll_enabled && tpl.is_active !== false).length, [templates])
  // The saved flag holds while realm and connector are as saved; an edit is judged live
  const saved = detail && form.realm.trim() === (detail.realm || '') && form.connector_id === detail.connector_id
  const checklist = profileChecklist(
    { ...(detail || {}), ...form, keytab_set: detail?.keytab_set, connector_id: form.connector_id,
      connector_domain_mismatch: saved ? Boolean(detail.connector_domain_mismatch) : realmMismatch,
      connector_enabled: connector?.enabled, connector_health: connector?.health?.state,
      issuing_ca_refid: form.issuing_ca_refid, realm: form.realm.trim() },
    { autoenrollTemplates })

  const pickKeytab = async (file) => {
    setKeytabFile(file)
    setKeytabPreview(null)
    if (!file || isNew) return
    // A dry run: the entries by realm are shown before anything is stored
    try {
      const response = await windowsProfilesService.uploadKeytab(profile.id, file, { dryRun: true })
      setKeytabPreview(response.data)
    } catch (error) {
      showError(error.message || t('xcepWstep.keytabUploadFailed'))
    }
  }

  const buildPayload = () => {
    const payload = {
      name: form.name.trim(),
      enabled: form.enabled,
      issuing_ca_refid: form.issuing_ca_refid || null,
      policy_ca_refid: form.policy_ca_refid || null,
      validity_days: Number(form.validity_days) || 365,
      allowed_ad_group: form.allowed_ad_group.trim() || null,
      pinned_subject_fields: form.pinned_subject_fields.trim() || null,
      template_ids: form.template_ids,
    }
    if (offerDefault && form.is_default) payload.is_default = true
    // Only the default profile's binding reads the shared accounts; the API refuses them elsewhere
    if (isDefault) {
      payload.xcep_username = form.xcep_username
      payload.wstep_username = form.wstep_username
    }
    // The API checks the realm/connector pair when either is sent: send them only when changed
    const realm = form.realm.trim()
    if (realm && (isNew || realm !== (detail?.realm || ''))) payload.realm = realm
    if (isNew || form.connector_id !== (detail?.connector_id ?? null)) payload.connector_id = form.connector_id
    if (isDefault && form.xcep_password) payload.xcep_password = form.xcep_password
    if (isDefault && form.wstep_password) payload.wstep_password = form.wstep_password
    return payload
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setTouched(true)
    if (form.realm.trim() && problemKey) {
      showError(t(problemKey))
      return
    }
    setSaving(true)
    try {
      const response = isNew
        ? await windowsProfilesService.create(buildPayload())
        : await windowsProfilesService.update(profile.id, buildPayload())
      const saved = response.data
      // The upload needs write:kerberos on top of write:xcep, which may be gone since the pick
      if (keytabFile && canUploadKeytab) {
        await windowsProfilesService.uploadKeytab(saved.id, keytabFile)
      }
      showSuccess(t('messages.success.update.settings'))
      onSaved(saved)
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setSaving(false)
    }
  }

  const readOnly = !canWrite
  const toggleTemplate = (id) => update('template_ids')(
    form.template_ids.includes(id) ? form.template_ids.filter(x => x !== id) : [...form.template_ids, id])
  const storedEntries = detail?.keytab_entries || []

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      {!form.enabled && !isNew && (
        <HelpCard variant="warning" title={t('xcepWstep.disabledTitle')}>
          {t('xcepWstep.disabledKeepsKeys')}
        </HelpCard>
      )}
      {!isNew && detail?.is_default && !detail.realm && (
        <HelpCard variant="warning" title={t('xcepWstep.noRealmTitle')}>
          {t('xcepWstep.noRealmKerberosRefused', { name: detail.name })}
        </HelpCard>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input
          label={t('xcepWstep.profileName')}
          value={form.name}
          onChange={(e) => update('name')(e.target.value)}
          maxLength={100}
          required
          disabled={readOnly}
        />
        <Input
          label={t('xcepWstep.realm')}
          value={form.realm}
          onChange={(e) => update('realm')(e.target.value)}
          onBlur={() => setTouched(true)}
          placeholder="CORP.EXAMPLE"
          error={realmError}
          helperText={t('xcepWstep.realmHelp')}
          disabled={readOnly}
        />
      </div>

      <ToggleSwitch
        label={t('common.enabled')}
        checked={form.enabled}
        onChange={update('enabled')}
        disabled={readOnly}
      />

      {offerDefault && (
        <label className="flex items-start gap-2 text-sm text-text-primary">
          <input
            type="checkbox"
            className="rounded mt-0.5"
            checked={form.is_default}
            onChange={(e) => update('is_default')(e.target.checked)}
            disabled={readOnly}
          />
          <span>
            {t('xcepWstep.makeDefault')}
            <span className="block text-xs text-text-tertiary">{t('xcepWstep.makeDefaultHelp')}</span>
          </span>
        </label>
      )}

      <Select
        label={t('xcepWstep.connector')}
        value={form.connector_id ? String(form.connector_id) : ''}
        onChange={(v) => update('connector_id')(v ? parseInt(v, 10) : null)}
        options={connectors.map(c => ({ value: String(c.id), label: c.realm ? `${c.name} (${c.realm})` : c.name }))}
        placeholder={t('xcepWstep.noConnector')}
        disabled={readOnly}
      />
      {realmMismatch && (
        <p className="text-xs status-warning-text" role="status">
          {t('xcepWstep.connectorRealmDiffers', { connector: connectorRealm, realm: form.realm.trim() })}
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Select
          label={t('xcepWstep.issuingCa')}
          value={form.issuing_ca_refid}
          onChange={update('issuing_ca_refid')}
          options={caOptions}
          helperText={caHelp}
          placeholder={t('xcepWstep.selectCa')}
          disabled={readOnly}
        />
        <Select
          label={t('xcepWstep.policyCa')}
          value={form.policy_ca_refid}
          onChange={update('policy_ca_refid')}
          options={caOptions}
          helperText={caHelp}
          placeholder={t('xcepWstep.policyCaSame')}
          disabled={readOnly}
        />
      </div>

      <Input
        label={t('xcepWstep.validityDays')}
        type="number"
        value={form.validity_days}
        onChange={(e) => update('validity_days')(e.target.value)}
        disabled={readOnly}
      />

      <div>
        <p className="text-xs font-medium text-text-secondary mb-1">{t('xcepWstep.templates')}</p>
        <p className="text-xs text-text-tertiary mb-2">{t('xcepWstep.templatesHelp')}</p>
        <div className="max-h-40 overflow-y-auto border border-border rounded-lg p-2 space-y-1">
          {templates.length === 0 && <p className="text-xs text-text-tertiary">{t('xcepWstep.noTemplates')}</p>}
          {templates.map(tpl => (
            <label key={tpl.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="rounded"
                checked={form.template_ids.includes(tpl.id)}
                onChange={() => toggleTemplate(tpl.id)}
                disabled={readOnly}
              />
              {tpl.name}
            </label>
          ))}
        </div>
      </div>

      <Input
        label={t('xcepWstep.allowedGroup')}
        value={form.allowed_ad_group}
        onChange={(e) => update('allowed_ad_group')(e.target.value)}
        helperText={t('xcepWstep.allowedGroupHelp')}
        disabled={readOnly}
      />
      <Textarea
        label={t('xcepWstep.pinnedFields')}
        value={form.pinned_subject_fields}
        onChange={(e) => update('pinned_subject_fields')(e.target.value)}
        rows={3}
        placeholder='{"O": "Example Corp"}'
        className="font-mono text-xs"
        helperText={t('xcepWstep.pinnedFieldsHelp')}
        disabled={readOnly}
      />

      {isDefault && (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input label={`${t('xcepWstep.xcepTitle')}: ${t('common.username')}`} value={form.xcep_username}
          onChange={(e) => update('xcep_username')(e.target.value)} disabled={readOnly} />
        <Input label={`${t('xcepWstep.xcepTitle')}: ${t('common.password')}`} type="password" value={form.xcep_password || ''}
          onChange={(e) => update('xcep_password')(e.target.value)}
          placeholder={detail?.xcep_password_set ? '••••••••' : ''} disabled={readOnly} />
        <Input label={`${t('xcepWstep.wstepTitle')}: ${t('common.username')}`} value={form.wstep_username}
          onChange={(e) => update('wstep_username')(e.target.value)} disabled={readOnly} />
        <Input label={`${t('xcepWstep.wstepTitle')}: ${t('common.password')}`} type="password" value={form.wstep_password || ''}
          onChange={(e) => update('wstep_password')(e.target.value)}
          placeholder={detail?.wstep_password_set ? '••••••••' : ''} disabled={readOnly} />
      </div>
      )}

      <div className="space-y-2 border border-border rounded-lg p-3">
        <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
          <Key size={16} /> {t('xcepWstep.keytab')}
          {detail?.keytab_set
            ? <Badge variant="success" size="sm">{t('xcepWstep.keytabSet')}</Badge>
            : <Badge variant="warning" size="sm">{t('xcepWstep.keytabNotSet')}</Badge>}
        </div>
        {detail?.keytab_error && <p className="text-xs status-danger-text">{detail.keytab_error}</p>}
        {storedEntries.length > 0 && <KeytabEntries entries={storedEntries} profileRealm={detail?.realm} />}
        {canWrite && canUploadKeytab && (
          <FileUpload
            label={t('xcepWstep.keytabReplace')}
            accept=".keytab,.kt"
            compact
            maxSize={256 * 1024}
            helperText={keytabFile ? t('xcepWstep.keytabSelected', { name: keytabFile.name }) : t('xcepWstep.keytabHelp')}
            onFileSelect={pickKeytab}
          />
        )}
        {keytabPreview && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-text-secondary">{t('xcepWstep.keytabPreview')}</p>
            <KeytabEntries entries={keytabPreview.keytab_entries} profileRealm={keytabPreview.profile_realm} />
            {keytabPreview.foreign_entries?.length > 0 && (
              <p className="text-xs status-danger-text" role="alert">
                {t('xcepWstep.keytabForeign', { entries: keytabPreview.foreign_entries.join(', ') })}
              </p>
            )}
          </div>
        )}
        {isNew && keytabFile && <p className="text-xs text-text-tertiary">{t('xcepWstep.keytabAfterSave')}</p>}
      </div>

      <div className="border border-border rounded-lg p-3">
        <div className="flex items-center gap-2 text-sm font-medium text-text-primary mb-1">
          <ListChecks size={16} /> {t('xcepWstep.checklistTitle')}
        </div>
        <div data-testid="profile-checklist">
          {checklist.map(item => (
            <ChecklistRow
              key={item.key}
              ok={item.ok}
              label={t(`xcepWstep.checklist.${item.key}`, item.count === undefined ? undefined : { count: item.count })}
              action={item.key === 'templates' ? t('common.configure') : undefined}
              onAction={item.key === 'templates' ? () => navigate('/templates') : undefined}
            />
          ))}
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>{t('common.cancel')}</Button>
        {canWrite && (
          <Button type="submit" disabled={saving}>
            {saving ? <ArrowsClockwise size={14} className="animate-spin" /> : <FloppyDisk size={14} />}
            {t('common.save')}
          </Button>
        )}
      </div>
    </form>
  )
}
