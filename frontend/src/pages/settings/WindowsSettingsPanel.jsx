import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Pill, RecordList } from '../../components/atelier'
import { Input, ToggleSwitch, Notice } from '../../components/atelier/Form'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { windowsProfilesService } from '../../services'
import { useNotification } from '../../contexts'
import { groupEntriesByRealm } from '../../lib/windowsProfile'
import CopyableUrl from './CopyableUrl'
import { useSavePart, keptPartDraft } from '../../hooks/useSaveParts'

function KeytabStatus({ settings, t }) {
  if (!settings.keytab_set) return null
  if (!settings.keytab_valid) {
    return <Pill tone="bad" label={t('xcepWstep.keytabInvalid', { error: settings.keytab_error })} />
  }
  const realms = groupEntriesByRealm(settings.keytab_entries).map(g => g.realm)
  return (
    <Pill tone="good" label={t('xcepWstep.keytabServed', { count: (settings.keytab_entries || []).length, realms: realms.join(', ') })} />
  )
}

/** Switches and SPN shared by every profile, the served keytab, and the URLs given once to all of them. */
export default function WindowsSettingsPanel({ hasPermission, onLoaded }) {
  const { t } = useTranslation()
  const { showWarning, showError } = useNotification()
  const baseUrl = typeof window !== 'undefined' ? window.location.origin : ''
  const [settings, setSettings] = useState(null)
  const [draft, setDraft] = useState({})
  const restored = useRef(false)
  const canWrite = hasPermission('write:xcep')

  const load = useCallback(async () => {
    try {
      const response = await windowsProfilesService.getSettings()
      setSettings(response.data)
      // A draft left pending on this tab comes back over what the server holds, once
      setDraft({
        xcep_enabled: Boolean(response.data.xcep_enabled),
        wstep_enabled: Boolean(response.data.wstep_enabled),
        kerberos_enabled: Boolean(response.data.kerberos_enabled),
        kerberos_spn: response.data.kerberos_spn || '',
        ...(restored.current ? {} : keptPartDraft('xcepWstep:shared')),
      })
      restored.current = true
      onLoaded?.(response.data)
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.generic'))
    }
  }, [onLoaded, showError, t])

  useEffect(() => { load() }, [load])

  const hasWstep = Boolean(settings && 'wstep_enabled' in settings)
  const hasKerberos = Boolean(settings && 'kerberos_enabled' in settings)
  const set = (field) => (value) => setDraft(prev => ({ ...prev, [field]: value }))
  const loaded = settings ? {
    xcep_enabled: Boolean(settings.xcep_enabled),
    wstep_enabled: Boolean(settings.wstep_enabled),
    kerberos_enabled: Boolean(settings.kerberos_enabled),
    kerberos_spn: settings.kerberos_spn || '',
  } : {}

  // Stored by the page's save bar, through the same route as before
  const handleSave = async () => {
    try {
      const payload = { xcep_enabled: draft.xcep_enabled }
      if (hasWstep && hasPermission('write:wstep')) payload.wstep_enabled = draft.wstep_enabled
      if (hasKerberos && hasPermission('write:kerberos')) {
        payload.kerberos_enabled = draft.kerberos_enabled
        payload.kerberos_spn = draft.kerberos_spn
      }
      const response = await windowsProfilesService.updateSettings(payload)
      if (response.data?.requires_container_restart || response.data?.restart_failed) showWarning(response.message)
      load()
      return { ok: true }
    } catch (error) {
      return { ok: false, message: error.message || t('messages.errors.updateFailed.settings') }
    }
  }

  useSavePart('xcepWstep:shared', {
    section: 'xcepWstep',
    count: settings ? Object.keys(loaded).filter((k) => draft[k] !== loaded[k]).length : 0,
    draft: settings ? draft : undefined,
    save: handleSave,
    reset: () => setDraft(loaded),
  })

  if (!settings) return null

  const defaultProfile = settings.default_profile
  const defaultWithoutRealm = Boolean(defaultProfile && defaultProfile.enabled && !defaultProfile.realm)

  return (
    <>
      <SettingsGroup legend={t('xcepWstep.sharedTitle')} hint={t('xcepWstep.sharedDescription')}>
        {defaultWithoutRealm && (
          <Notice tone="warn"><strong>{t('xcepWstep.noRealmTitle')}</strong>{' '}{t('xcepWstep.noRealmKerberosRefused', { name: defaultProfile.name })}</Notice>
        )}
        {hasKerberos && !settings.library_available && (
          <Notice tone="warn">
            <strong>{t('xcepWstep.kerberosLibraryWarningTitle')}</strong>{' '}{t('xcepWstep.kerberosLibraryWarningDesc')}{' '}{t('xcepWstep.kerberosLibraryWarningFix')}
            <span className="command-line"><code>apt-get install libkrb5-dev build-essential python3-dev && pip install pyspnego[kerberos]</code></span>
          </Notice>
        )}
        <ToggleSwitch label={t('xcepWstep.xcepTitle')} description={t('xcepWstep.xcepDescription')}
          checked={Boolean(draft.xcep_enabled)} disabled={!canWrite} onChange={set('xcep_enabled')} />
        {hasWstep && (
          <ToggleSwitch label={t('xcepWstep.wstepTitle')} description={t('xcepWstep.wstepDescription')}
            checked={Boolean(draft.wstep_enabled)} disabled={!hasPermission('write:wstep')} onChange={set('wstep_enabled')} />
        )}
        {hasKerberos && (
          <>
            <ToggleSwitch label={t('xcepWstep.kerberosTitle')} description={t('xcepWstep.kerberosDescription')}
              checked={Boolean(draft.kerberos_enabled)} disabled={!hasPermission('write:kerberos')} onChange={set('kerberos_enabled')} />
            <Input id="set-kerberos_spn" label={t('xcepWstep.spn')} value={draft.kerberos_spn} disabled={!hasPermission('write:kerberos')}
              onChange={(e) => set('kerberos_spn')(e.target.value)} placeholder={t('xcepWstep.spnPlaceholder')} />
            <div className="field">
              <span>{t('xcepWstep.keytab')}</span>
              <span className="row-actions">
                <KeytabStatus settings={settings} t={t} />
                {!settings.keytab_set && <Pill tone="warn" label={t('xcepWstep.keytabNoneServed')} />}
              </span>
            </div>
          </>
        )}
      </SettingsGroup>

      {settings.xcep_enabled && (
        <SettingsGroup legend={t('xcepWstep.urlsTitle')} hint={t('xcepWstep.urlsRoutedByRealm')} grid={false}>
          <RecordList>
            <CopyableUrl
              label={t('xcepWstep.urlUsernamePassword')}
              value={`${baseUrl}/ADPolicyProvider_CEP_UsernamePassword/service.svc`}
              description={t('xcepWstep.urlUsernamePasswordDesc')}
            />
            <CopyableUrl
              label={t('xcepWstep.urlKerberos')}
              value={`${baseUrl}/ADPolicyProvider_CEP_Kerberos/service.svc`}
              description={t('xcepWstep.urlKerberosDesc')}
            />
          </RecordList>
        </SettingsGroup>
      )}
    </>
  )
}
