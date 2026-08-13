import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { WindowsLogo, Globe, Certificate, ArrowsClockwise, FloppyDisk, CheckCircle, WarningCircle, XCircle, ListChecks, Key } from '@phosphor-icons/react'
import { Badge, Button, Input, Select, DetailHeader, DetailSection, DetailContent, HelpCard } from '../../components'
import { FileUpload } from '../../components/FileUpload'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { xcepWstepService, casService, adConnectorService, kerberosService, templatesService } from '../../services'
import { useNotification } from '../../contexts'
import CopyableUrl from './CopyableUrl'

const EMPTY_XCEP = { enabled: false, ca_id: null, username: '', password_set: false }
const EMPTY_WSTEP = { enabled: false, ca_id: null, username: '', password_set: false, validity_days: 365 }

function KeytabStatusBadge({ kerberos, t }) {
  if (!kerberos.keytab_set) return null
  if (!kerberos.keytab_valid) {
    return (
      <Badge variant="danger" icon={XCircle}>
        {t('xcepWstep.keytabInvalid', { error: kerberos.keytab_error })}
      </Badge>
    )
  }
  if (!kerberos.keytab_spn_matches) {
    return (
      <Badge variant="warning" icon={WarningCircle}>
        {t('xcepWstep.keytabSpnMismatch', { principal: kerberos.keytab_principal })}
      </Badge>
    )
  }
  return (
    <Badge variant="success" icon={CheckCircle}>
      {t('xcepWstep.keytabValid', { principal: kerberos.keytab_principal })}
    </Badge>
  )
}

function StatusRow({ ok, label, actionLabel, onAction }) {
  return (
    <div className="flex items-center justify-between gap-2 py-1.5">
      <div className="flex items-center gap-2">
        {ok ? (
          <CheckCircle size={16} weight="fill" className="text-emerald-500 shrink-0" />
        ) : (
          <WarningCircle size={16} weight="fill" className="text-amber-500 shrink-0" />
        )}
        <span className="text-sm text-text-primary">{label}</span>
      </div>
      {!ok && onAction && (
        <Button type="button" size="sm" variant="ghost" onClick={onAction}>{actionLabel}</Button>
      )}
    </div>
  )
}

export default function XcepWstepSection() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const navigate = useNavigate()
  const baseUrl = typeof window !== 'undefined' ? window.location.origin : ''

  const [cas, setCas] = useState([])
  const [loading, setLoading] = useState(true)

  const [xcep, setXcep] = useState(EMPTY_XCEP)
  const [xcepPassword, setXcepPassword] = useState('')
  const [xcepSaving, setXcepSaving] = useState(false)

  const [wstep, setWstep] = useState(EMPTY_WSTEP)
  const [wstepPassword, setWstepPassword] = useState('')
  const [wstepSaving, setWstepSaving] = useState(false)

  const [kerberos, setKerberos] = useState({
    enabled: false, spn: '', keytab_set: false, library_available: true,
    keytab_valid: false, keytab_principal: null, keytab_error: null, keytab_spn_matches: false,
  })
  const [kerberosSpnInput, setKerberosSpnInput] = useState('')
  const [kerberosKeytabFile, setKerberosKeytabFile] = useState(null)
  const [kerberosSaving, setKerberosSaving] = useState(false)

  // Setup checklist state -- read-only status pulled from the other
  // settings surfaces (AD Connector, Kerberos, Templates) that a full GPO
  // autoenrollment setup touches, so an admin can see what's still missing
  // from one place instead of discovering it template by template.
  const [adConnectorConfigured, setAdConnectorConfigured] = useState(false)
  const [kerberosConfigured, setKerberosConfigured] = useState(false)
  const [autoenrollTemplateCount, setAutoenrollTemplateCount] = useState(0)

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [casRes, xcepRes, wstepRes, adRes, krbRes, tplRes] = await Promise.all([
        casService.getAll(),
        xcepWstepService.getXcep(),
        xcepWstepService.getWstep(),
        adConnectorService.get().catch(() => ({ data: null })),
        kerberosService.get().catch(() => ({ data: null })),
        templatesService.getAll().catch(() => ({ data: [] })),
      ])
      setCas(casRes.data || [])
      setXcep(xcepRes.data || EMPTY_XCEP)
      setWstep(wstepRes.data || EMPTY_WSTEP)
      setAdConnectorConfigured(Boolean(adRes.data?.enabled && adRes.data?.server))
      setKerberosConfigured(Boolean(krbRes.data?.configured))
      if (krbRes.data) {
        setKerberos(krbRes.data)
        setKerberosSpnInput(krbRes.data.spn || '')
      }
      const templates = tplRes.data || []
      setAutoenrollTemplateCount(templates.filter(tpl => tpl.autoenroll_enabled).length)
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.generic'))
    } finally {
      setLoading(false)
    }
  }, [showError, t])

  useEffect(() => { loadAll() }, [loadAll])

  const caOptions = cas.map(ca => ({ value: String(ca.id), label: ca.descr || ca.common_name }))

  const handleXcepSave = async () => {
    setXcepSaving(true)
    try {
      const payload = { enabled: xcep.enabled, ca_id: xcep.ca_id, username: xcep.username }
      if (xcepPassword) payload.password = xcepPassword
      await xcepWstepService.updateXcep(payload)
      showSuccess(t('messages.success.update.settings'))
      setXcepPassword('')
      loadAll()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setXcepSaving(false)
    }
  }

  const handleWstepSave = async () => {
    setWstepSaving(true)
    try {
      const payload = { enabled: wstep.enabled, ca_id: wstep.ca_id, username: wstep.username, validity_days: wstep.validity_days }
      if (wstepPassword) payload.password = wstepPassword
      await xcepWstepService.updateWstep(payload)
      showSuccess(t('messages.success.update.settings'))
      setWstepPassword('')
      loadAll()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setWstepSaving(false)
    }
  }

  const handleKerberosSave = async () => {
    setKerberosSaving(true)
    try {
      await kerberosService.update({ enabled: kerberos.enabled, spn: kerberosSpnInput })
      if (kerberosKeytabFile) {
        await kerberosService.uploadKeytab(kerberosKeytabFile)
        setKerberosKeytabFile(null)
      }
      showSuccess(t('messages.success.update.settings'))
      loadAll()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setKerberosSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-6 h-6 border-2 border-accent-primary-op30 border-t-accent-primary rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <DetailContent>
      <DetailHeader
        icon={WindowsLogo}
        title={t('xcepWstep.title')}
        subtitle={t('xcepWstep.subtitle')}
      />

      <DetailSection title={t('xcepWstep.checklistTitle')} icon={ListChecks} iconClass="icon-bg-emerald">
        <div className="space-y-3">
          <div>
            <p className="text-xs font-medium text-text-secondary mb-1">{t('xcepWstep.checklistManual')}</p>
            <StatusRow ok={cas.length > 0} label={t('xcepWstep.checklistCa')} />
            <StatusRow ok={xcep.enabled} label={t('xcepWstep.checklistXcep')} />
            <StatusRow ok={wstep.enabled} label={t('xcepWstep.checklistWstep')} />
          </div>
          <div className="pt-2 border-t border-border">
            <p className="text-xs font-medium text-text-secondary mb-1">{t('xcepWstep.checklistGpo')}</p>
            <StatusRow
              ok={adConnectorConfigured}
              label={t('xcepWstep.checklistAdConnector')}
              actionLabel={t('common.configure')}
              onAction={() => navigate('/settings?tab=adConnector')}
            />
            <StatusRow
              ok={kerberosConfigured}
              label={t('xcepWstep.checklistKerberos')}
            />
            <StatusRow
              ok={autoenrollTemplateCount > 0}
              label={t('xcepWstep.checklistTemplates', { count: autoenrollTemplateCount })}
              actionLabel={t('common.configure')}
              onAction={() => navigate('/templates')}
            />
          </div>
        </div>
      </DetailSection>

      <DetailSection title={t('xcepWstep.xcepTitle')} icon={Globe} iconClass="icon-bg-cyan">
        <div className="space-y-4">
          <p className="text-xs text-text-secondary">{t('xcepWstep.xcepDescription')}</p>
          <ToggleSwitch
            label={t('common.enabled')}
            checked={xcep.enabled}
            onChange={(val) => setXcep(prev => ({ ...prev, enabled: val }))}
          />
          <Select
            label={t('xcepWstep.ca')}
            value={xcep.ca_id ? String(xcep.ca_id) : ''}
            onChange={(val) => setXcep(prev => ({ ...prev, ca_id: val ? parseInt(val, 10) : null }))}
            options={caOptions}
            placeholder={t('xcepWstep.selectCa')}
          />
          <div className="grid grid-cols-2 gap-4">
            <Input
              label={t('common.username')}
              value={xcep.username || ''}
              onChange={(e) => setXcep(prev => ({ ...prev, username: e.target.value }))}
            />
            <Input
              label={t('common.password')}
              type="password"
              value={xcepPassword}
              onChange={(e) => setXcepPassword(e.target.value)}
              placeholder={xcep.password_set ? '••••••••' : ''}
            />
          </div>
          <div className="flex justify-end pt-4 border-t border-border">
            <Button type="button" onClick={handleXcepSave} disabled={xcepSaving}>
              {xcepSaving ? <ArrowsClockwise size={14} className="animate-spin" /> : <FloppyDisk size={14} />}
              {t('common.save')}
            </Button>
          </div>
        </div>
      </DetailSection>

      <DetailSection title={t('xcepWstep.wstepTitle')} icon={Certificate} iconClass="icon-bg-blue">
        <div className="space-y-4">
          <p className="text-xs text-text-secondary">{t('xcepWstep.wstepDescription')}</p>
          <ToggleSwitch
            label={t('common.enabled')}
            checked={wstep.enabled}
            onChange={(val) => setWstep(prev => ({ ...prev, enabled: val }))}
          />
          <Select
            label={t('xcepWstep.ca')}
            value={wstep.ca_id ? String(wstep.ca_id) : ''}
            onChange={(val) => setWstep(prev => ({ ...prev, ca_id: val ? parseInt(val, 10) : null }))}
            options={caOptions}
            placeholder={t('xcepWstep.selectCa')}
          />
          <div className="grid grid-cols-2 gap-4">
            <Input
              label={t('common.username')}
              value={wstep.username || ''}
              onChange={(e) => setWstep(prev => ({ ...prev, username: e.target.value }))}
            />
            <Input
              label={t('common.password')}
              type="password"
              value={wstepPassword}
              onChange={(e) => setWstepPassword(e.target.value)}
              placeholder={wstep.password_set ? '••••••••' : ''}
            />
          </div>
          <Input
            label={t('xcepWstep.validityDays')}
            type="number"
            value={wstep.validity_days || 365}
            onChange={(e) => setWstep(prev => ({ ...prev, validity_days: parseInt(e.target.value, 10) || 365 }))}
          />
          <div className="flex justify-end pt-4 border-t border-border">
            <Button type="button" onClick={handleWstepSave} disabled={wstepSaving}>
              {wstepSaving ? <ArrowsClockwise size={14} className="animate-spin" /> : <FloppyDisk size={14} />}
              {t('common.save')}
            </Button>
          </div>
        </div>
      </DetailSection>

      <DetailSection title={t('xcepWstep.kerberosTitle')} icon={Key} iconClass="icon-bg-amber">
        <div className="space-y-4">
          <p className="text-xs text-text-secondary">{t('xcepWstep.kerberosDescription')}</p>

          {!kerberos.library_available && (
            <HelpCard variant="warning" title={t('xcepWstep.kerberosLibraryWarningTitle')}>
              <p>{t('xcepWstep.kerberosLibraryWarningDesc')}</p>
              <p className="mt-2">{t('xcepWstep.kerberosLibraryWarningFix')}</p>
              <code className="block mt-1 text-[11px] font-mono text-text-primary bg-bg-tertiary px-2 py-1.5 rounded break-all">
                apt-get install libkrb5-dev build-essential python3-dev && pip install pyspnego[kerberos]
              </code>
            </HelpCard>
          )}
          {!adConnectorConfigured && (
            <HelpCard variant="warning" title={t('xcepWstep.kerberosAdConnectorWarningTitle')}>
              {t('xcepWstep.kerberosAdConnectorWarningDesc')}
            </HelpCard>
          )}

          <ToggleSwitch
            label={t('common.enabled')}
            checked={kerberos.enabled}
            onChange={(val) => setKerberos(prev => ({ ...prev, enabled: val }))}
          />
          <Input
            label={t('xcepWstep.spn')}
            value={kerberosSpnInput}
            onChange={(e) => setKerberosSpnInput(e.target.value)}
            placeholder={t('xcepWstep.spnPlaceholder')}
          />
          <FileUpload
            label={`${t('xcepWstep.keytab')} ${kerberos.keytab_set ? `(${t('xcepWstep.keytabSet')})` : `(${t('xcepWstep.keytabNotSet')})`}`}
            accept=".keytab,.kt"
            compact
            maxSize={256 * 1024}
            helperText={kerberosKeytabFile ? t('xcepWstep.keytabSelected', { name: kerberosKeytabFile.name }) : t('xcepWstep.keytabHelp')}
            onFileSelect={(file) => setKerberosKeytabFile(file)}
          />
          <KeytabStatusBadge kerberos={kerberos} t={t} />
          <div className="flex justify-end pt-4 border-t border-border">
            <Button type="button" onClick={handleKerberosSave} disabled={kerberosSaving}>
              {kerberosSaving ? <ArrowsClockwise size={14} className="animate-spin" /> : <FloppyDisk size={14} />}
              {t('common.save')}
            </Button>
          </div>
        </div>
      </DetailSection>

      {xcep.enabled && (
        <DetailSection title={t('xcepWstep.urlsTitle')} icon={Globe} iconClass="icon-bg-violet">
          <div className="space-y-3">
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
    </DetailContent>
  )
}
