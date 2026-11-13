import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Globe, Key, ArrowsClockwise, FloppyDisk, CheckCircle, WarningCircle, XCircle } from '@phosphor-icons/react'
import { Badge, Button, Input, DetailSection, HelpCard } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { windowsProfilesService } from '../../services'
import { useNotification } from '../../contexts'
import { groupEntriesByRealm } from '../../lib/windowsProfile'
import CopyableUrl from './CopyableUrl'

function KeytabStatus({ settings, t }) {
  if (!settings.keytab_set) return null
  if (!settings.keytab_valid) {
    return <Badge variant="danger" icon={XCircle}>{t('xcepWstep.keytabInvalid', { error: settings.keytab_error })}</Badge>
  }
  const realms = groupEntriesByRealm(settings.keytab_entries).map(g => g.realm)
  return (
    <Badge variant="success" icon={CheckCircle}>
      {t('xcepWstep.keytabServed', { count: (settings.keytab_entries || []).length, realms: realms.join(', ') })}
    </Badge>
  )
}

/** Switches and SPN shared by every profile, the served keytab, and the URLs given once to all of them. */
export default function WindowsSettingsPanel({ hasPermission, onLoaded }) {
  const { t } = useTranslation()
  const { showSuccess, showWarning, showError } = useNotification()
  const baseUrl = typeof window !== 'undefined' ? window.location.origin : ''
  const [settings, setSettings] = useState(null)
  const [draft, setDraft] = useState({})
  const [saving, setSaving] = useState(false)
  const canWrite = hasPermission('write:xcep')

  const load = useCallback(async () => {
    try {
      const response = await windowsProfilesService.getSettings()
      setSettings(response.data)
      setDraft({
        xcep_enabled: Boolean(response.data.xcep_enabled),
        wstep_enabled: Boolean(response.data.wstep_enabled),
        kerberos_enabled: Boolean(response.data.kerberos_enabled),
        kerberos_spn: response.data.kerberos_spn || '',
      })
      onLoaded?.(response.data)
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.generic'))
    }
  }, [onLoaded, showError, t])

  useEffect(() => { load() }, [load])

  if (!settings) return null

  const hasWstep = 'wstep_enabled' in settings
  const hasKerberos = 'kerberos_enabled' in settings
  const set = (field) => (value) => setDraft(prev => ({ ...prev, [field]: value }))

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = { xcep_enabled: draft.xcep_enabled }
      if (hasWstep && hasPermission('write:wstep')) payload.wstep_enabled = draft.wstep_enabled
      if (hasKerberos && hasPermission('write:kerberos')) {
        payload.kerberos_enabled = draft.kerberos_enabled
        payload.kerberos_spn = draft.kerberos_spn
      }
      const response = await windowsProfilesService.updateSettings(payload)
      if (response.data?.requires_container_restart || response.data?.restart_failed) showWarning(response.message)
      else showSuccess(response.message || t('messages.success.update.settings'))
      load()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setSaving(false)
    }
  }

  const defaultProfile = settings.default_profile
  const defaultWithoutRealm = Boolean(defaultProfile && defaultProfile.enabled && !defaultProfile.realm)

  return (
    <>
      <DetailSection title={t('xcepWstep.sharedTitle')} icon={Key} iconClass="icon-bg-amber">
        <div className="space-y-4">
          <p className="text-xs text-text-secondary">{t('xcepWstep.sharedDescription')}</p>

          {defaultWithoutRealm && (
            <HelpCard variant="warning" title={t('xcepWstep.noRealmTitle')}>
              {t('xcepWstep.noRealmKerberosRefused', { name: defaultProfile.name })}
            </HelpCard>
          )}
          {hasKerberos && !settings.library_available && (
            <HelpCard variant="warning" title={t('xcepWstep.kerberosLibraryWarningTitle')}>
              <p>{t('xcepWstep.kerberosLibraryWarningDesc')}</p>
              <p className="mt-2">{t('xcepWstep.kerberosLibraryWarningFix')}</p>
              <code className="block mt-1 text-xs font-mono text-text-primary bg-bg-tertiary px-2 py-1.5 rounded break-all">
                apt-get install libkrb5-dev build-essential python3-dev && pip install pyspnego[kerberos]
              </code>
            </HelpCard>
          )}

          <ToggleSwitch
            label={t('xcepWstep.xcepTitle')}
            description={t('xcepWstep.xcepDescription')}
            checked={Boolean(draft.xcep_enabled)}
            disabled={!canWrite}
            onChange={set('xcep_enabled')}
          />
          {hasWstep && (
            <ToggleSwitch
              label={t('xcepWstep.wstepTitle')}
              description={t('xcepWstep.wstepDescription')}
              checked={Boolean(draft.wstep_enabled)}
              disabled={!hasPermission('write:wstep')}
              onChange={set('wstep_enabled')}
            />
          )}
          {hasKerberos && (
            <>
              <ToggleSwitch
                label={t('xcepWstep.kerberosTitle')}
                description={t('xcepWstep.kerberosDescription')}
                checked={Boolean(draft.kerberos_enabled)}
                disabled={!hasPermission('write:kerberos')}
                onChange={set('kerberos_enabled')}
              />
              <Input
                label={t('xcepWstep.spn')}
                value={draft.kerberos_spn}
                disabled={!hasPermission('write:kerberos')}
                onChange={(e) => set('kerberos_spn')(e.target.value)}
                placeholder={t('xcepWstep.spnPlaceholder')}
              />
              <div className="flex items-center gap-2 flex-wrap">
                <KeytabStatus settings={settings} t={t} />
                {!settings.keytab_set && (
                  <Badge variant="warning" icon={WarningCircle}>{t('xcepWstep.keytabNoneServed')}</Badge>
                )}
              </div>
            </>
          )}
          {canWrite && (
            <div className="flex justify-end pt-4 border-t border-border">
              <Button type="button" onClick={handleSave} disabled={saving}>
                {saving ? <ArrowsClockwise size={14} className="animate-spin" /> : <FloppyDisk size={14} />}
                {t('common.save')}
              </Button>
            </div>
          )}
        </div>
      </DetailSection>

      {settings.xcep_enabled && (
        <DetailSection title={t('xcepWstep.urlsTitle')} icon={Globe} iconClass="icon-bg-violet">
          <div className="space-y-3">
            <p className="text-xs text-text-secondary">{t('xcepWstep.urlsRoutedByRealm')}</p>
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
          </div>
        </DetailSection>
      )}
    </>
  )
}
