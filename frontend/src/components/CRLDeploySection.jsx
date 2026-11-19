import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CloudArrowUp, Plus, Trash, UploadSimple, PencilSimple } from '@phosphor-icons/react'
import { Badge, Button, CompactSection } from './index'
import { Modal } from './Modal'
import { deployService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { extractData, formatDate } from '../lib/utils'

const STATUS_VARIANT = { delivered: 'success', pending: 'warning', failed: 'danger' }

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

  return (
    <>
      <CompactSection title={t('crlDeploy.title', 'CRL deployment')} icon={CloudArrowUp}>
        <p className="text-xs text-text-tertiary mb-3">
          {t('crlDeploy.description', 'Push every updated complete CRL to an SSH deployment target.')}
        </p>
        {loading ? (
          <div className="text-xs text-text-tertiary">{t('common.loading')}</div>
        ) : bindings.length === 0 ? (
          <p className="text-xs text-text-tertiary italic">
            {t('crlDeploy.none', 'This CA is not deployed to any target.')}
          </p>
        ) : (
          <div className="space-y-2">
            {bindings.map(binding => (
              <div key={binding.id}
                className="p-2 rounded-md bg-bg-tertiary border border-border">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-text-primary truncate">
                        {binding.target_name}
                      </span>
                      {!binding.enabled ? (
                        <Badge variant="secondary" size="sm">{t('common.disabled')}</Badge>
                      ) : binding.last_delivery ? (
                        <Badge variant={STATUS_VARIANT[binding.last_delivery.status] || 'secondary'} size="sm"
                          title={binding.last_delivery.last_error || ''}>
                          {t(`deploy.status.${binding.last_delivery.status}`)}
                        </Badge>
                      ) : (
                        <Badge variant="secondary" size="sm">{t('common.enabled')}</Badge>
                      )}
                    </div>
                    <code className="block text-xs text-text-secondary break-all mt-1">
                      {binding.crl_path}
                    </code>
                    <p className="text-xs text-text-tertiary mt-1">
                      {binding.format.toUpperCase()}
                      {binding.include_parent_crls
                        ? ` · ${t('crlDeploy.withParents', 'includes parent CRLs')}` : ''}
                    </p>
                    {binding.reload_command && (
                      <p className="text-xs text-text-tertiary font-mono truncate mt-1"
                        title={binding.reload_command}>
                        {t('deploy.reloadCommand', 'Reload command')}: {binding.reload_command}
                      </p>
                    )}
                    {binding.last_delivery?.delivered_at && (
                      <p className="text-2xs text-text-tertiary">
                        {t('deploy.lastDeployed', { date: formatDate(binding.last_delivery.delivered_at) })}
                      </p>
                    )}
                    {binding.last_delivery?.status === 'pending' && binding.last_delivery.next_attempt_at && (
                      <p className="text-2xs text-text-tertiary">
                        {t('deploy.nextRetry', {
                          date: formatDate(binding.last_delivery.next_attempt_at),
                          countdown: retryCountdown(binding.last_delivery.next_attempt_at, now),
                        })}
                      </p>
                    )}
                    {binding.last_delivery?.last_error && (
                      <p className={`text-2xs truncate ${binding.last_delivery.status === 'failed'
                        ? 'status-danger-text' : 'status-warning-text'}`}
                        title={binding.last_delivery.last_error}>
                        {binding.last_delivery.last_error}
                      </p>
                    )}
                  </div>
                  {(canWriteDeploy || canDeleteDeploy) && (
                    <div className="flex gap-1 shrink-0">
                      {canWriteDeploy && (
                        <Button type="button" size="xs" variant="secondary"
                          data-deploy-binding-edit="crl"
                          onClick={() => edit(binding)} title={t('common.edit')}>
                          <PencilSimple size={14} />
                        </Button>
                      )}
                      {canWriteDeploy && (
                        <Button type="button" size="xs" variant="secondary"
                          onClick={() => deployNow(binding)} disabled={deploying === binding.id}
                          title={t('crlDeploy.deployNow', 'Deploy now')}>
                          <UploadSimple size={14} />
                        </Button>
                      )}
                      {canDeleteDeploy && (
                        <Button type="button" size="xs" variant="ghost"
                          onClick={() => remove(binding)} title={t('common.remove')}>
                          <Trash size={14} />
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        {canWriteDeploy && hasCRL && (
          <Button type="button" size="sm" variant="secondary" className="mt-3"
            onClick={() => { setEditing(null); setForm(EMPTY); setOpen(true) }}
            disabled={availableTargets.length === 0}>
            <Plus size={14} /> {t('crlDeploy.attach', 'Attach target')}
          </Button>
        )}
      </CompactSection>

      <Modal open={open} onOpenChange={value => {
          if (!saving) { setOpen(value); if (!value) setEditing(null) }
        }}
        title={editing
          ? t('deploy.editDeploymentFor', { name: ca?.descr || ca?.name })
          : t('crlDeploy.attachFor', 'Attach CRL target: {{name}}', { name: ca?.descr || ca?.name })}
        size="sm">
        <form onSubmit={create} className="p-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">
              {t('deploy.target', 'Target')}
            </label>
            <select required value={form.target_id} disabled={Boolean(editing)}
              onChange={event => setForm({ ...form, target_id: event.target.value })}
              className="w-full rounded-md border border-border bg-bg-primary text-text-primary text-sm p-2">
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
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">
              {t('crlDeploy.path', 'CRL destination path')}
            </label>
            <input required value={form.crl_path}
              onChange={event => setForm({ ...form, crl_path: event.target.value })}
              className="w-full rounded-md border border-border bg-bg-primary text-text-primary text-sm font-mono p-2"
              placeholder="/root/certs/CRL.crl" />
          </div>
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">
              {t('export.format')}
            </label>
            <select value={form.format}
              onChange={event => setForm({
                ...form, format: event.target.value,
                include_parent_crls: event.target.value === 'pem' && form.include_parent_crls,
              })}
              className="w-full rounded-md border border-border bg-bg-primary text-text-primary text-sm p-2">
              <option value="pem">PEM</option>
              <option value="der">DER</option>
            </select>
          </div>
          {form.format === 'pem' && (
            <label className="flex items-start gap-2 rounded-md border border-border p-3">
              <input type="checkbox" className="mt-0.5" checked={form.include_parent_crls}
                onChange={event => setForm({ ...form, include_parent_crls: event.target.checked })} />
              <span>
                <span className="block text-sm font-medium text-text-primary">
                  {t('crlDeploy.includeParents', 'Include parent CRLs')}
                </span>
                <span className="block text-xs text-text-tertiary">
                  {t('crlDeploy.includeParentsHelp', 'Creates a PEM bundle containing this CA CRL followed by issuer CRLs.')}
                </span>
              </span>
            </label>
          )}
          <label className="flex items-start gap-2 rounded-md border border-border p-3">
            <input type="checkbox" className="mt-0.5" checked={form.enabled}
              onChange={event => setForm({ ...form, enabled: event.target.checked })} />
            <span className="block text-sm font-medium text-text-primary">
              {t('common.enabled')}
            </span>
          </label>
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">
              {t('deploy.reloadCommand', 'Reload command')}
            </label>
            <input value={form.reload_command}
              onChange={event => setForm({ ...form, reload_command: event.target.value })}
              className="w-full rounded-md border border-border bg-bg-primary text-text-primary text-sm font-mono p-2"
              placeholder="/usr/sbin/nginx -t && /usr/sbin/nginx -s reload"
              maxLength={512} />
            <p className="text-2xs text-text-tertiary mt-1">
              {t('deploy.reloadCommandHint')}
            </p>
          </div>
          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button type="button" variant="secondary"
              onClick={() => { setOpen(false); setEditing(null) }} disabled={saving}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={saving || !form.target_id}>
              {editing ? t('common.save') : t('crlDeploy.attach', 'Attach target')}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  )
}
