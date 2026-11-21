/**
 * The discovery dialogs in the mockup's form dialog: an analysis (a scan profile) to create or
 * edit, a quick scan, and the removal confirmations.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Btn, Icon } from '../../components/atelier'
import { PORT_PRESETS, SCHEDULES, MAX_RANGE_HOSTS, portsOf, splitList, targetProblem, targetsOf, validPorts } from './discoveryModel'

const clamp = (v, lo, hi, d) => Math.min(Math.max(parseInt(v, 10) || d, lo), hi)

/** `profile` given: edit it; `quick`: a scan run once, saved nowhere. */
export function ScanDialog({ quick = false, profile, busy, onSubmit, onClose, returnTo }) {
  const { t, i18n } = useTranslation()
  const [f, setF] = useState(() => ({
    name: profile?.name || '',
    description: profile?.description || '',
    targets: profile ? targetsOf(profile).join('\n') : '',
    ports: profile ? portsOf(profile).join(', ') : '443',
    schedule: String(profile?.schedule_interval_minutes || 0),
    notify_email: profile?.notify_email || '',
    notify_on_new: profile?.notify_on_new !== false,
    notify_on_change: profile?.notify_on_change !== false,
    notify_on_expiry: profile?.notify_on_expiry !== false,
    resolve_dns: !!profile?.resolve_dns,
    timeout: profile?.timeout || 5,
    max_workers: profile?.max_workers || 20,
  }))
  const [tried, setTried] = useState(false)
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }))
  const targets = splitList(f.targets)
  const problems = targets.map((x) => [x, targetProblem(x)]).filter(([, p]) => p)
  const ports = validPorts(f.ports)
  const scheduled = Number(f.schedule) > 0
  const errs = {
    name: !quick && tried && !f.name.trim() ? t('discovery.form.nameRequired') : null,
    targets: problems.length
      ? problems.map(([x, p]) => t(`discovery.form.problem.${p}`, { target: x, max: new Intl.NumberFormat(i18n?.language).format(MAX_RANGE_HOSTS) })).join(' ')
      : tried && !targets.length ? t('discovery.form.targetsRequired') : null,
    ports: splitList(f.ports).length && ports.length !== splitList(f.ports).length ? t('discovery.invalidPort') : null,
  }
  const blocked = Object.values(errs).some(Boolean)

  const submit = (e) => {
    e.preventDefault()
    setTried(true)
    if ((!quick && !f.name.trim()) || !targets.length || blocked) {
      document.getElementById(!quick && !f.name.trim() ? 'scan-name' : 'scan-targets')?.focus()
      return
    }
    const common = { targets, ports: ports.length ? ports : [443], timeout: f.timeout, max_workers: f.max_workers, resolve_dns: f.resolve_dns }
    onSubmit(quick ? common : {
      ...common,
      name: f.name.trim(),
      description: f.description.trim(),
      schedule_interval_minutes: Number(f.schedule),
      schedule_enabled: scheduled,
      notify_email: f.notify_email.trim() || null,
      notify_on_new: f.notify_on_new,
      notify_on_change: f.notify_on_change,
      notify_on_expiry: f.notify_on_expiry,
    })
  }
  const error = (id, text) => text && <p className="field-error" id={`err-${id}`}><Icon name="warning" /><span>{text}</span></p>
  const described = (id, text) => (text ? `hint-${id} err-${id}` : `hint-${id}`)
  const check = (k, label) => (
    <label className="checkbox-line">
      <input type="checkbox" name={k} checked={f[k]} onChange={(e) => set(k, e.target.checked)} /><span>{label}</span>
    </label>
  )
  const preset = PORT_PRESETS.find((p) => p.ports.join(', ') === splitList(f.ports).join(', '))?.id || ''
  const title = quick ? t('discovery.quickScanAsk') : profile ? t('discovery.editProfile') : t('discovery.scans.create')

  return (
    <AtelierDialog title={title} subtitle={profile?.name} onClose={onClose} returnTo={returnTo} testId={quick ? 'quick-scan-dialog' : 'scan-profile-dialog'}>
      <form id="scan-form" noValidate onSubmit={submit}>
        <div className="form-fields">
          {!quick && (
            <>
              <div className="field full">
                <label htmlFor="scan-name">{t('common.name')}</label>
                <input id="scan-name" value={f.name} required maxLength={100} data-autofocus="" placeholder={t('discovery.profileNamePlaceholder')}
                  aria-invalid={errs.name ? true : undefined} aria-describedby={errs.name ? 'err-scan-name' : undefined}
                  onChange={(e) => set('name', e.target.value)} />
                {error('scan-name', errs.name)}
              </div>
              <div className="field full">
                <label htmlFor="scan-desc">{t('common.description')} <span className="optional">{t('common.optional')}</span></label>
                <input id="scan-desc" value={f.description} maxLength={500} onChange={(e) => set('description', e.target.value)} />
              </div>
            </>
          )}
          <div className="field full">
            <label htmlFor="scan-targets">{t('discovery.form.range')}</label>
            <textarea id="scan-targets" className="mono" rows={4} value={f.targets} spellCheck={false} data-autofocus={quick ? '' : undefined}
              placeholder={'192.0.2.0/24\nweb.example.com\nmail.example.com:465'}
              aria-invalid={errs.targets ? true : undefined} aria-describedby={described('scan-targets', errs.targets)}
              onChange={(e) => set('targets', e.target.value)} />
            {error('scan-targets', errs.targets)}
            <small id="hint-scan-targets">{t('discovery.form.rangeHint')}</small>
          </div>
          <div className="field">
            <label htmlFor="scan-preset">{t('discovery.form.preset')}</label>
            <select id="scan-preset" value={preset} onChange={(e) => { const p = PORT_PRESETS.find((x) => x.id === e.target.value); if (p) set('ports', p.ports.join(', ')) }}>
              <option value="">{t('discovery.form.presetOther')}</option>
              {PORT_PRESETS.map((p) => <option key={p.id} value={p.id}>{t(`discovery.form.presets.${p.id}`)}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="scan-ports">{t('discovery.ports')}</label>
            <input id="scan-ports" value={f.ports} spellCheck={false}
              aria-invalid={errs.ports ? true : undefined} aria-describedby={described('scan-ports', errs.ports)}
              onChange={(e) => set('ports', e.target.value)} />
            {error('scan-ports', errs.ports)}
            <small id="hint-scan-ports">{t('discovery.portsHelp')}</small>
          </div>
          {!quick && (
            <div className="field">
              <label htmlFor="scan-schedule">{t('discovery.schedule')}</label>
              <select id="scan-schedule" value={f.schedule} onChange={(e) => set('schedule', e.target.value)}>
                {SCHEDULES.map((m) => <option key={m} value={String(m)}>{t(`discovery.form.every.${m}`)}</option>)}
              </select>
            </div>
          )}
          {!quick && scheduled && (
            <>
              <div className="field">
                <label htmlFor="scan-email">{t('discovery.notifyEmail')} <span className="optional">{t('common.optional')}</span></label>
                <input id="scan-email" type="email" value={f.notify_email} placeholder="pki@example.com" aria-describedby="hint-scan-email"
                  onChange={(e) => set('notify_email', e.target.value)} />
                <small id="hint-scan-email">{t('discovery.notifyEmailHelper')}</small>
              </div>
              <fieldset className="field full">
                <legend>{t('discovery.notifyEvents')}</legend>
                <div className="eku-list">
                  {check('notify_on_new', t('discovery.notifyOnNew'))}
                  {check('notify_on_change', t('discovery.notifyOnChange'))}
                  {check('notify_on_expiry', t('discovery.notifyOnExpiry'))}
                </div>
              </fieldset>
            </>
          )}
          <div className="field">
            <label htmlFor="scan-timeout">{t('discovery.timeout')}</label>
            <input id="scan-timeout" type="number" min={1} max={30} value={f.timeout} aria-describedby="hint-scan-timeout"
              onChange={(e) => set('timeout', clamp(e.target.value, 1, 30, 5))} />
            <small id="hint-scan-timeout">{t('discovery.form.timeoutHint')}</small>
          </div>
          <div className="field">
            <label htmlFor="scan-workers">{t('discovery.concurrency')}</label>
            <input id="scan-workers" type="number" min={1} max={50} value={f.max_workers} aria-describedby="hint-scan-workers"
              onChange={(e) => set('max_workers', clamp(e.target.value, 1, 50, 20))} />
            <small id="hint-scan-workers">{t('discovery.form.workersHint')}</small>
          </div>
          <div className="field full">{check('resolve_dns', t('discovery.reverseDns'))}</div>
        </div>
        <div className="modal-actions">
          <Btn data-action="close-modal" onClick={onClose}>{t('common.cancel')}</Btn>
          <Btn type="submit" tone="primary" icon={quick ? 'radar' : profile ? 'check' : 'plus'} id="scan-submit" disabled={busy || blocked || undefined}>
            {quick ? t('discovery.startScan') : profile ? t('common.save') : t('common.create')}
          </Btn>
        </div>
      </form>
    </AtelierDialog>
  )
}

/** A removal: what goes, then Annuler and the danger action. */
export function RemoveDialog({ title, subtitle, text, confirm, busy, onConfirm, onClose, returnTo }) {
  const { t } = useTranslation()
  return (
    <AtelierDialog title={title} subtitle={subtitle} size="narrow" onClose={onClose} returnTo={returnTo} testId="discovery-remove-dialog">
      <div className="notice warn"><Icon name="warning" /><span>{text}</span></div>
      <div className="modal-actions">
        <Btn data-action="close-modal" onClick={onClose}>{t('common.cancel')}</Btn>
        <Btn tone="danger" icon="block" id="discovery-remove-confirm" disabled={busy || undefined} onClick={onConfirm}>{confirm}</Btn>
      </div>
    </AtelierDialog>
  )
}
