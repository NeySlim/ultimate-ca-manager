import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Btn, Pill, RecordList, RecordRow } from '../../components/atelier'
import { Input, NumberInput, SecretInput, Select, Textarea, ToggleSwitch, Notice } from '../../components/atelier/Form'
import { FieldError } from '../../components/atelier/SettingsView'
import { windowsProfilesService, adConnectorsService, templatesService } from '../../services'
import { useNotification } from '../../contexts'
import { pickerCas, unlistedPickerCas } from '../../lib/caSelection'
import {
  realmProblem, realmOfBaseDn, groupEntriesByRealm, foreignRealms, profileChecklist,
} from '../../lib/windowsProfile'

const EMPTY = {
  name: '', realm: '', enabled: true, connector_id: null, issuing_ca_refid: '', policy_ca_refid: '',
  validity_days: 365, allowed_ad_group: '', pinned_subject_fields: '', template_ids: [],
  xcep_username: '', wstep_username: '', is_default: false, renewal_ca_refids: [],
}

// The keytab a profile accepts: Kerberos keytabs are small, the server refuses more
const KEYTAB_MAX = 256 * 1024

/** The keytab entries of a profile, grouped by realm, the realm that is not the profile's flagged. */
export function KeytabEntries({ entries, profileRealm }) {
  const { t } = useTranslation()
  const groups = groupEntriesByRealm(entries)
  const foreign = new Set(foreignRealms(entries, profileRealm))
  if (!groups.length) return <p className="muted small">{t('xcepWstep.keytabNoEntries')}</p>
  return (
    <div data-testid="keytab-entries">
      <RecordList>
        {groups.map(({ realm, entries: list }) => (
          <RecordRow key={realm} title={<span className="mono">{realm}</span>}
            extra={list.map((entry, index) => (
              <span key={`${entry.principal}-${entry.kvno}-${entry.enctype}-${index}`} className="rl-meta mono">
                {entry.principal} (kvno {entry.kvno}, etype {entry.enctype})
              </span>
            ))}
            badge={foreign.has(realm)
              ? <Pill tone="bad" label={t('xcepWstep.keytabRealmDiffers', { realm: profileRealm || '-' })} />
              : <Pill tone="good" label={t('xcepWstep.keytabRealmMatches')} />} />
        ))}
      </RecordList>
    </div>
  )
}

export default function WindowsProfileEditor({ profile, cas, canWrite, canUploadKeytab, onSaved, onCancel }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { showSuccess, showError, showInfo } = useNotification()
  const isNew = !profile?.id
  const [detail, setDetail] = useState(null)
  const [form, setForm] = useState({ ...EMPTY })
  const [connectors, setConnectors] = useState([])
  const [templates, setTemplates] = useState([])
  const [saving, setSaving] = useState(false)
  const [keytabFile, setKeytabFile] = useState(null)
  const [keytabPreview, setKeytabPreview] = useState(null)
  const [keytabError, setKeytabError] = useState(null)
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
            renewal_ca_refids: (p.renewal_cas || []).map(ca => ca.refid),
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
    setKeytabError(null)
    if (file && file.size > KEYTAB_MAX) {
      setKeytabFile(null)
      setKeytabPreview(null)
      setKeytabError(t('xcepWstep.keytabTooLarge'))
      return
    }
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
    else if (!realm && !isNew && detail?.realm) payload.realm = null
    if (isNew || form.connector_id !== (detail?.connector_id ?? null)) payload.connector_id = form.connector_id
    if (isDefault && form.xcep_password) payload.xcep_password = form.xcep_password
    if (isDefault && form.wstep_password) payload.wstep_password = form.wstep_password
    // The API only takes former CAs off the list; sent when the operator removed one
    const listed = (detail?.renewal_cas || []).map(ca => ca.refid)
    if (!isNew && form.renewal_ca_refids.length !== listed.length) payload.renewal_ca_refids = form.renewal_ca_refids
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
      // The TLS listener reloads the former CAs it trusts on a restart
      if (saved?.restart_message) showInfo(saved.restart_message)
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

  // The mockup's dialog form: the profile's fields in `.form-fields`, the keytab and the checklist as record lists
  return (
    <form onSubmit={handleSubmit}>
      <div className="form-fields">
        {!form.enabled && !isNew && (
          <Notice tone="warn"><strong>{t('xcepWstep.disabledTitle')}</strong>{' '}{t('xcepWstep.disabledKeepsKeys')}</Notice>
        )}
        {!isNew && detail?.is_default && !detail.realm && (
          <Notice tone="warn"><strong>{t('xcepWstep.noRealmTitle')}</strong>{' '}{t('xcepWstep.noRealmKerberosRefused', { name: detail.name })}</Notice>
        )}

        <Input id="wp-name" label={t('xcepWstep.profileName')} value={form.name} onChange={(e) => update('name')(e.target.value)}
          maxLength={100} required disabled={readOnly} data-autofocus="" />
        <Input id="wp-realm" label={t('xcepWstep.realm')} value={form.realm} onChange={(e) => update('realm')(e.target.value)}
          onBlur={() => setTouched(true)} placeholder="CORP.EXAMPLE" error={realmError} hint={t('xcepWstep.realmHelp')} disabled={readOnly} />

        <ToggleSwitch label={t('common.enabled')} checked={form.enabled} onChange={update('enabled')} disabled={readOnly} />
        {offerDefault && (
          <ToggleSwitch label={t('xcepWstep.makeDefault')} description={t('xcepWstep.makeDefaultHelp')}
            checked={form.is_default} onChange={update('is_default')} disabled={readOnly} />
        )}

        <Select id="wp-connector" full label={t('xcepWstep.connector')} value={form.connector_id ? String(form.connector_id) : ''}
          onChange={(v) => update('connector_id')(v ? parseInt(v, 10) : null)}
          options={[{ value: '', label: t('xcepWstep.noConnector') },
            ...connectors.map(c => ({ value: String(c.id), label: c.realm ? `${c.name} (${c.realm})` : c.name }))]}
          disabled={readOnly} />
        {realmMismatch && (
          <Notice tone="warn" role="status">{t('xcepWstep.connectorRealmDiffers', { connector: connectorRealm, realm: form.realm.trim() })}</Notice>
        )}

        <Select id="wp-issuing-ca" label={t('xcepWstep.issuingCa')} value={form.issuing_ca_refid} onChange={update('issuing_ca_refid')}
          options={caOptions} hint={caHelp} placeholder={t('xcepWstep.selectCa')} disabled={readOnly} />
        <Select id="wp-policy-ca" label={t('xcepWstep.policyCa')} value={form.policy_ca_refid} onChange={update('policy_ca_refid')}
          options={[{ value: '', label: t('xcepWstep.policyCaSame') }, ...caOptions]} hint={caHelp} disabled={readOnly} />

        {!isNew && (
          <fieldset className="field full" aria-describedby="hint-wp-renewal">
            <legend>{t('xcepWstep.renewalCas')}</legend>
            <small id="hint-wp-renewal">{t('xcepWstep.renewalCasHelp')}</small>
            <RecordList empty={t('xcepWstep.renewalCasNone')}>
              {form.renewal_ca_refids.length > 0 && (detail?.renewal_cas || []).filter(ca => form.renewal_ca_refids.includes(ca.refid)).map(ca => (
                <RecordRow key={ca.refid} title={ca.name || `${t('xcepWstep.renewalCaDeleted')} (${ca.refid})`}
                  action={<Btn disabled={readOnly || undefined}
                    onClick={() => update('renewal_ca_refids')(form.renewal_ca_refids.filter(r => r !== ca.refid))}>
                    {t('xcepWstep.renewalCaRemove')}
                  </Btn>} />
              ))}
            </RecordList>
          </fieldset>
        )}

        <NumberInput id="wp-validity" label={t('xcepWstep.validityDays')} value={form.validity_days}
          onChange={(e) => update('validity_days')(e.target.value)} disabled={readOnly} />
        <Input id="wp-group" label={t('xcepWstep.allowedGroup')} value={form.allowed_ad_group}
          onChange={(e) => update('allowed_ad_group')(e.target.value)} hint={t('xcepWstep.allowedGroupHelp')} disabled={readOnly} />

        <fieldset className="field full" aria-describedby="hint-wp-templates">
          <legend>{t('xcepWstep.templates')}</legend>
          <small id="hint-wp-templates">{t('xcepWstep.templatesHelp')}</small>
          {templates.length === 0
            ? <p className="muted small">{t('xcepWstep.noTemplates')}</p>
            : (
              <div className="columns-list">
                {templates.map(tpl => (
                  <label key={tpl.id} className="checkbox-line">
                    <input type="checkbox" checked={form.template_ids.includes(tpl.id)} onChange={() => toggleTemplate(tpl.id)} disabled={readOnly} />
                    {tpl.name}
                  </label>
                ))}
              </div>
            )}
        </fieldset>

        <Textarea id="wp-pinned" label={t('xcepWstep.pinnedFields')} value={form.pinned_subject_fields}
          onChange={(e) => update('pinned_subject_fields')(e.target.value)} rows={3} placeholder='{"O": "Example Corp"}' mono
          hint={t('xcepWstep.pinnedFieldsHelp')} disabled={readOnly} />

        {isDefault && (
          <>
            <Input id="wp-xcep-user" label={`${t('xcepWstep.xcepTitle')}${t('work.sep')}${t('common.username')}`} value={form.xcep_username}
              onChange={(e) => update('xcep_username')(e.target.value)} disabled={readOnly} />
            <SecretInput id="wp-xcep-password" label={`${t('xcepWstep.xcepTitle')}${t('work.sep')}${t('common.password')}`} value={form.xcep_password || ''}
              onChange={(e) => update('xcep_password')(e.target.value)} placeholder={detail?.xcep_password_set ? '••••••••' : ''} disabled={readOnly} />
            <Input id="wp-wstep-user" label={`${t('xcepWstep.wstepTitle')}${t('work.sep')}${t('common.username')}`} value={form.wstep_username}
              onChange={(e) => update('wstep_username')(e.target.value)} disabled={readOnly} />
            <SecretInput id="wp-wstep-password" label={`${t('xcepWstep.wstepTitle')}${t('work.sep')}${t('common.password')}`} value={form.wstep_password || ''}
              onChange={(e) => update('wstep_password')(e.target.value)} placeholder={detail?.wstep_password_set ? '••••••••' : ''} disabled={readOnly} />
          </>
        )}

        <fieldset className="field full">
          <legend>
            {t('xcepWstep.keytab')}{' '}
            {detail?.keytab_set ? <Pill tone="good" label={t('xcepWstep.keytabSet')} /> : <Pill tone="warn" label={t('xcepWstep.keytabNotSet')} />}
          </legend>
          {detail?.keytab_error && <FieldError id="err-wp-keytab-stored" message={detail.keytab_error} />}
          {storedEntries.length > 0 && <KeytabEntries entries={storedEntries} profileRealm={detail?.realm} />}
          {canWrite && canUploadKeytab && (
            <div className="field">
              <label htmlFor="wp-keytab">{t('xcepWstep.keytabReplace')}</label>
              <input id="wp-keytab" type="file" accept=".keytab,.kt" aria-describedby="hint-wp-keytab"
                aria-invalid={keytabError ? 'true' : undefined} onChange={(e) => pickKeytab(e.target.files?.[0] || null)} />
              <small id="hint-wp-keytab">{keytabFile ? t('xcepWstep.keytabSelected', { name: keytabFile.name }) : t('xcepWstep.keytabHelp')}</small>
              {keytabError && <FieldError id="err-wp-keytab" message={keytabError} />}
            </div>
          )}
          {keytabPreview && (
            <>
              <small>{t('xcepWstep.keytabPreview')}</small>
              <KeytabEntries entries={keytabPreview.keytab_entries} profileRealm={keytabPreview.profile_realm} />
              {keytabPreview.foreign_entries?.length > 0 && (
                <Notice tone="bad">{t('xcepWstep.keytabForeign', { entries: keytabPreview.foreign_entries.join(', ') })}</Notice>
              )}
            </>
          )}
          {isNew && keytabFile && <small>{t('xcepWstep.keytabAfterSave')}</small>}
        </fieldset>

        <fieldset className="field full">
          <legend>{t('xcepWstep.checklistTitle')}</legend>
          <div data-testid="profile-checklist">
            <RecordList>
              {checklist.map(item => (
                <RecordRow key={item.key}
                  title={t(`xcepWstep.checklist.${item.key}`, item.count === undefined ? undefined : { count: item.count })}
                  badge={item.ok ? <Pill tone="good" label={t('common.ok')} /> : <Pill tone="warn" label={t('xcepWstep.checklistMissing')} />}
                  action={!item.ok && item.key === 'templates'
                    ? <Btn onClick={() => navigate('/templates')}>{t('common.configure')}</Btn>
                    : null} />
              ))}
            </RecordList>
          </div>
        </fieldset>
      </div>

      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
        {canWrite && (
          <Btn type="submit" tone="primary" icon="check" disabled={saving || undefined}>{t('common.save')}</Btn>
        )}
      </div>
    </form>
  )
}
