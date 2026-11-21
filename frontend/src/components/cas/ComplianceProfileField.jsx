/**
 * Compliance profile of a CA, with the actions to attach, change or remove it.
 * Attaching or changing runs the profile preflight on this CA first, shows its
 * findings, and asks for an explicit confirmation before the PATCH.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SideField, SideAction } from './SideField'
import { AtelierDialog, Icon } from '../atelier'
import { Select } from '../atelier/Form'
import PreflightReport from '../PreflightReport'
import { casService, systemService } from '../../services'
import { useNotification } from '../../contexts/NotificationContext'
import { COMPLIANCE_PROFILE_NAMES, useComplianceProfiles } from '../../lib/complianceProfiles'

const VERDICT = {
  ready: 'cas.compliance.ready',
  notReady: 'cas.compliance.notReady',
  nothingFound: 'cas.compliance.nothingFound',
}

function profileLabel(name, profiles) {
  const p = profiles[name]
  return p ? `${p.title} (${p.reference})` : name
}

// Attaching needs admin:system too: the preflight shown first requires it
export function ComplianceProfileField({ ca, canWrite = false, canAttach = false, onChanged }) {
  const { t } = useTranslation()
  const profiles = useComplianceProfiles()
  const current = COMPLIANCE_PROFILE_NAMES.includes(ca.compliance_profile) ? ca.compliance_profile : ''

  return (
    <SideField label={t('cas.complianceProfile')}>
      <span>{current ? profileLabel(current, profiles) : t('cas.complianceProfileNone')}</span>
      {canWrite && !ca.revoked && (
        <ProfileActions ca={ca} current={current} profiles={profiles} canAttach={canAttach} onChanged={onChanged} />
      )}
    </SideField>
  )
}

function ProfileActions({ ca, current, profiles, canAttach, onChanged }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const [dialog, setDialog] = useState(false)

  const apply = async (profile) => {
    const res = await casService.update(ca.id, { complianceProfile: profile })
    const updated = res?.data || res
    showSuccess(t('cas.compliance.changed'))
    if (updated?.id) onChanged?.(updated)
    window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
  }

  const handleRemove = async () => {
    const confirmed = await showConfirm(t('cas.compliance.removeConfirm'), {
      title: t('cas.complianceProfile'), confirmText: t('cas.compliance.remove'), variant: 'danger',
    })
    if (!confirmed) return
    try {
      await apply(null)
    } catch (err) {
      showError(err?.message || t('cas.compliance.changeFailed'))
    }
  }

  return (
    <>
      {canAttach && (
        <SideAction onClick={() => setDialog(true)}>
          {t(current ? 'cas.compliance.change' : 'cas.compliance.attach')}
        </SideAction>
      )}
      {current && (
        <SideAction onClick={handleRemove}>
          {t('cas.compliance.remove')}
        </SideAction>
      )}
      {dialog && (
        <AttachProfileDialog
          ca={ca}
          current={current}
          profiles={profiles}
          onClose={() => setDialog(false)}
          onConfirm={async (profile) => { await apply(profile); setDialog(false) }}
        />
      )}
    </>
  )
}

function AttachProfileDialog({ ca, current, profiles, onClose, onConfirm }) {
  const { t } = useTranslation()
  const { showError } = useNotification()
  const [profile, setProfile] = useState('')
  const [report, setReport] = useState(null)
  const [checking, setChecking] = useState(false)
  const [checkError, setCheckError] = useState(null)
  const [saving, setSaving] = useState(false)
  const latest = useRef(0)

  // Only the last choice's report counts
  useEffect(() => {
    const run = ++latest.current
    setReport(null)
    setCheckError(null)
    if (!profile) return
    setChecking(true)
    Promise.resolve()
      .then(() => systemService.getCompliancePreflight(profile, ca.id))
      .then((res) => { if (run === latest.current) setReport(res?.data ?? res) })
      .catch((err) => { if (run === latest.current) setCheckError(err?.message || t('cas.compliance.checkFailed')) })
      .finally(() => { if (run === latest.current) setChecking(false) })
  }, [profile, ca.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const confirm = async () => {
    setSaving(true)
    try {
      await onConfirm(profile)
    } catch (err) {
      showError(err?.message || t('cas.compliance.changeFailed'))
      setSaving(false)
    }
  }

  const options = COMPLIANCE_PROFILE_NAMES.filter(n => n !== current)
    .map(n => ({ value: n, label: profileLabel(n, profiles) }))
  const label = profile ? profileLabel(profile, profiles) : ''

  const close = () => { if (!saving) onClose() }

  return (
    <AtelierDialog title={t('cas.complianceProfile')} onClose={close} testId="compliance-attach-dialog">
      <div className="form-fields">
        <Select id="compliance-profile-pick" label={t('cas.compliance.pickProfile')} options={options} value={profile} full
          placeholder={t('cas.compliance.pickPlaceholder')} onChange={setProfile} data-autofocus="" />
      </div>
      {checking && <p className="small muted" role="status" style={{ marginTop: 16 }}>{t('cas.compliance.checking')}</p>}
      {checkError && <p role="alert" className="field-error" style={{ marginTop: 16 }}><Icon name="warning" /><span>{checkError}</span></p>}
      {report && (
        <div style={{ marginTop: 18 }}>
          <PreflightReport atelier report={report} testId="compliance-attach-report" verdict={VERDICT} />
        </div>
      )}
      {report && (
        <p className="event-detail" style={{ marginTop: 16 }} data-testid="compliance-attach-statement">
          {t('cas.compliance.confirmAttach', { profile: label })}
        </p>
      )}
      <div className="modal-actions">
        <button type="button" className="btn" onClick={close} disabled={saving || undefined}>{t('common.cancel')}</button>
        <button type="button" className="btn primary" data-write="" onClick={confirm} disabled={!report || checking || saving || undefined}>
          {saving ? t('common.loading') : t('cas.compliance.confirmButton', { profile: label })}
        </button>
      </div>
    </AtelierDialog>
  )
}
