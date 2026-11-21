import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, IconBtn, Pill, Section, RecordList, RecordRow, AtelierDialog } from './atelier'
import { deployService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { extractData, formatDate } from '../lib/utils'

const STATUS_TONE = { delivered: 'good', pending: 'warn', failed: 'bad' }

function retryCountdown(nextAttemptAt, now) {
  const milliseconds = new Date(nextAttemptAt).getTime() - now
  if (!Number.isFinite(milliseconds)) return ''
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000))
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return minutes > 0 ? `${minutes}m ${String(remainingSeconds).padStart(2, '0')}s` : `${seconds}s`
}

const EMPTY = {
  target_id: '', crl_path: '', format: 'pem',
  include_parent_crls: true, reload_command: '', enabled: true,
}

export function CRLDeploySection({ ca, hasCRL }) {
  const { t } = useTranslation()
  const { hasPermission } = usePermission()
  const { showSuccess, showError, showConfirm } = useNotification()
  const [bindings, setBindings] = useState([])
  const [targets, setTargets] = useState([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [saving, setSaving] = useState(false)
  const [deploying, setDeploying] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [now, setNow] = useState(() => Date.now())
  const canReadDeploy = hasPermission('read:deploy')
  const canWriteDeploy = hasPermission('write:deploy')
  const canDeleteDeploy = hasPermission('delete:deploy')

  const sequence = useRef(0)   // only the newest load may fill the section
  const load = useCallback(async (silent = false) => {
    if (!ca?.id || !canReadDeploy) return
    const seq = ++sequence.current
    if (!silent) setLoading(true)
    try {
      const [bindingRes, targetRes] = await Promise.all([
        deployService.getCRLBindings({ ca_id: ca.id }),
        deployService.getTargets(),
      ])
      if (seq !== sequence.current) return
      setBindings(extractData(bindingRes) || [])
      // CRLs are files: an HTTP target (#428) carries certificates only
      setTargets((extractData(targetRes) || []).filter(target => target.enabled && target.kind !== 'http'))
    } catch (error) {
      if (!silent) {
        showError(error.message || t('crlDeploy.loadFailed', 'Failed to load CRL deployments'))
      }
    } finally {
      if (!silent) setLoading(false)
    }
  }, [ca?.id, canReadDeploy, showError, t])

  useEffect(() => { load() }, [load])

  const hasPendingDelivery = bindings.some(binding =>
    binding.last_delivery?.status === 'pending' && binding.last_delivery?.next_attempt_at)
  useEffect(() => {
    if (!hasPendingDelivery) return undefined
    setNow(Date.now())
    const countdownInterval = setInterval(() => setNow(Date.now()), 1000)
    const refreshInterval = setInterval(() => load(true), 5000)
    return () => {
      clearInterval(countdownInterval)
      clearInterval(refreshInterval)
    }
  }, [hasPendingDelivery, load])

  const create = async (event) => {
    event.preventDefault()
    setSaving(true)
    try {
      const payload = {
        crl_path: form.crl_path.trim(), format: form.format,
        include_parent_crls: form.include_parent_crls,
        reload_command: form.reload_command.trim(), enabled: form.enabled,
      }
      if (editing) {
        await deployService.updateCRLBinding(editing.id, payload)
        showSuccess(t('common.updated'))
      } else {
        await deployService.createCRLBinding({
          ...payload, target_id: Number(form.target_id), ca_id: ca.id,
        })
        showSuccess(t('crlDeploy.created', 'CRL deployment attached and initial push queued'))
      }
      setOpen(false)
      setEditing(null)
      setForm(EMPTY)
      await load()
    } catch (error) {
      showError(error.message || t('crlDeploy.createFailed', 'Failed to attach CRL deployment'))
    } finally {
      setSaving(false)
    }
  }

  const edit = (binding) => {
    setEditing(binding)
    setForm({
      target_id: String(binding.target_id),
      crl_path: binding.crl_path,
      format: binding.format,
      include_parent_crls: Boolean(binding.include_parent_crls),
      reload_command: binding.reload_command || '',
      enabled: binding.enabled,
    })
    setOpen(true)
  }

  const remove = async (binding) => {
    const confirmed = await showConfirm(
      t('crlDeploy.deleteConfirm', 'Remove this CRL deployment?'),
      { title: t('crlDeploy.remove', 'Remove CRL deployment'), variant: 'danger' })
    if (!confirmed) return
    try {
      await deployService.deleteCRLBinding(binding.id)
      showSuccess(t('crlDeploy.removed', 'CRL deployment removed'))
      await load()
    } catch (error) {
      showError(error.message || t('crlDeploy.deleteFailed', 'Failed to remove CRL deployment'))
    }
  }

  const deployNow = async (binding) => {
    setDeploying(binding.id)
    try {
      await deployService.deployCRLNow(binding.id)
      showSuccess(t('crlDeploy.deployed', 'CRL deployed successfully'))
      await load()
    } catch (error) {
      showError(error.message || t('crlDeploy.deployFailed', 'CRL deployment failed'))
    } finally {
      setDeploying(null)
    }
  }

  const availableTargets = targets.filter(
    target => !bindings.some(binding => binding.target_id === target.id))

  if (!canReadDeploy) return null

  const close = () => { if (!saving) { setOpen(false); setEditing(null) } }
  const badge = (binding) => (!binding.enabled
    ? <Pill label={t('common.disabled')} tone="muted" />
    : binding.last_delivery
      ? <Pill label={t(`deploy.status.${binding.last_delivery.status}`)} tone={STATUS_TONE[binding.last_delivery.status] || 'muted'} />
      : <Pill label={t('common.enabled')} tone="good" />)

  // The CRL deployment of an authority, drawn as a section of the CRL / OCSP dock (the mockup's record rows)
  return (
    <>
      <Section title={t('crlDeploy.title', 'CRL deployment')}>
        <p className="muted small">{t('crlDeploy.description', 'Push every updated complete CRL to an SSH deployment target.')}</p>
        {loading ? (
          <p className="muted small">{t('common.loading')}</p>
        ) : (
          <RecordList empty={t('crlDeploy.none', 'This CA is not deployed to any target.')}>
            {bindings.map(binding => (
              <RecordRow key={binding.id} title={binding.target_name} badge={badge(binding)}
                meta={<><span className="mono">{binding.crl_path}</span>{' · '}{binding.format.toUpperCase()}
                  {binding.include_parent_crls ? ` · ${t('crlDeploy.withParents', 'includes parent CRLs')}` : ''}</>}
                extra={<>
                  {binding.reload_command && (
                    <span className="rl-meta" title={binding.reload_command}>
                      {t('deploy.reloadCommand', 'Reload command')}: <span className="mono">{binding.reload_command}</span>
                    </span>
                  )}
                  {binding.last_delivery?.delivered_at && (
                    <span className="rl-meta">{t('deploy.lastDeployed', { date: formatDate(binding.last_delivery.delivered_at) })}</span>
                  )}
                  {binding.last_delivery?.status === 'pending' && binding.last_delivery.next_attempt_at && (
                    <span className="rl-meta">
                      {t('deploy.nextRetry', {
                        date: formatDate(binding.last_delivery.next_attempt_at),
                        countdown: retryCountdown(binding.last_delivery.next_attempt_at, now),
                      })}
                    </span>
                  )}
                  {binding.last_delivery?.last_error && (
                    <p className="rl-error" title={binding.last_delivery.last_error}><span>{binding.last_delivery.last_error}</span></p>
                  )}
                </>}
                action={(canWriteDeploy || canDeleteDeploy) && (
                  <>
                    {canWriteDeploy && (
                      <IconBtn quiet icon="settings" write data-deploy-binding-edit="crl" label={t('common.edit')} onClick={() => edit(binding)} />
                    )}
                    {canWriteDeploy && (
                      <IconBtn quiet icon="upload" write label={t('crlDeploy.deployNow', 'Deploy now')}
                        disabled={deploying === binding.id || undefined} onClick={() => deployNow(binding)} />
                    )}
                    {canDeleteDeploy && <IconBtn quiet icon="close" write label={t('common.remove')} onClick={() => remove(binding)} />}
                  </>
                )} />
            ))}
          </RecordList>
        )}
        {canWriteDeploy && hasCRL && (
          <div className="copy-url">
            <Btn icon="plus" write id="crl-deploy-attach" disabled={availableTargets.length === 0 || undefined}
              onClick={() => { setEditing(null); setForm(EMPTY); setOpen(true) }}>
              {t('crlDeploy.attach', 'Attach target')}
            </Btn>
          </div>
        )}
      </Section>

      {open && (
        <AtelierDialog size="narrow" onClose={close} returnTo="crl-deploy-attach"
          title={editing
            ? t('deploy.editDeploymentFor', { name: ca?.descr || ca?.name })
            : t('crlDeploy.attachFor', 'Attach CRL target: {{name}}', { name: ca?.descr || ca?.name })}>
          <form onSubmit={create}>
            <div className="form-fields">
              <div className="field full">
                <label htmlFor="crl-deploy-target">{t('deploy.target', 'Target')}</label>
                <select id="crl-deploy-target" required value={form.target_id} disabled={Boolean(editing) || undefined}
                  onChange={event => setForm({ ...form, target_id: event.target.value })}>
                  {editing ? (
                    <option value={editing.target_id}>{editing.target_name} ({editing.target_host})</option>
                  ) : (
                    <>
                      <option value="">{t('deploy.selectTarget', 'Select a target...')}</option>
                      {availableTargets.map(target => (
                        <option key={target.id} value={target.id}>{target.name} ({target.host})</option>
                      ))}
                    </>
                  )}
                </select>
              </div>
              <div className="field full">
                <label htmlFor="crl-deploy-path">{t('crlDeploy.path', 'CRL destination path')}</label>
                <input id="crl-deploy-path" className="mono" required value={form.crl_path}
                  onChange={event => setForm({ ...form, crl_path: event.target.value })}
                  placeholder="/root/certs/CRL.crl" />
              </div>
              <div className="field">
                <label htmlFor="crl-deploy-format">{t('export.format')}</label>
                <select id="crl-deploy-format" value={form.format}
                  onChange={event => setForm({
                    ...form, format: event.target.value,
                    include_parent_crls: event.target.value === 'pem' && form.include_parent_crls,
                  })}>
                  <option value="pem">PEM</option>
                  <option value="der">DER</option>
                </select>
              </div>
              {form.format === 'pem' && (
                <div className="field full">
                  <label className="checkbox-line">
                    <input type="checkbox" checked={form.include_parent_crls} aria-describedby="crl-deploy-parents-hint"
                      onChange={event => setForm({ ...form, include_parent_crls: event.target.checked })} />
                    {t('crlDeploy.includeParents', 'Include parent CRLs')}
                  </label>
                  <small id="crl-deploy-parents-hint">
                    {t('crlDeploy.includeParentsHelp', 'Creates a PEM bundle containing this CA CRL followed by issuer CRLs.')}
                  </small>
                </div>
              )}
              <div className="field full">
                <label className="checkbox-line">
                  <input type="checkbox" checked={form.enabled}
                    onChange={event => setForm({ ...form, enabled: event.target.checked })} />
                  {t('common.enabled')}
                </label>
              </div>
              <div className="field full">
                <label htmlFor="crl-deploy-reload">{t('deploy.reloadCommand', 'Reload command')}</label>
                <input id="crl-deploy-reload" className="mono" value={form.reload_command} aria-describedby="crl-deploy-reload-hint"
                  onChange={event => setForm({ ...form, reload_command: event.target.value })}
                  placeholder="/usr/sbin/nginx -t && /usr/sbin/nginx -s reload" maxLength={512} />
                <small id="crl-deploy-reload-hint">{t('deploy.reloadCommandHint')}</small>
              </div>
            </div>
            <div className="modal-actions">
              <Btn onClick={close} disabled={saving || undefined}>{t('common.cancel')}</Btn>
              <Btn type="submit" tone="primary" icon="check" disabled={saving || !form.target_id || undefined}>
                {editing ? t('common.save') : t('crlDeploy.attach', 'Attach target')}
              </Btn>
            </div>
          </form>
        </AtelierDialog>
      )}
    </>
  )
}
