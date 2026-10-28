/**
 * CertDeploySection — deployment block on the certificate detail view (#299).
 *
 * Shows the certificate's deploy bindings (target + destination paths + last
 * delivery status), lets an admin attach a target, push now, or detach.
 * Renders nothing for non-admin users or certificates without a cert.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CloudArrowUp, Plus, Trash, ArrowsClockwise, PencilSimple } from '@phosphor-icons/react'
import { Badge } from '../Badge'
import { Button } from '../Button'
import { CompactSection } from '../DetailCard'
import { Modal } from '../Modal'
import { ChainVariantSelect, variantLabel } from '../ChainVariantSelect'
import { fetchChainVariants } from '../../lib/crossCertificates'
import { deployService } from '../../services'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks'
import { extractData, formatDate } from '../../lib/utils'

const STATUS_VARIANT = { delivered: 'success', pending: 'warning', failed: 'danger' }

export function CertDeploySection({ certificate }) {
  const { t } = useTranslation()
  const { hasPermission } = usePermission()
  const { showSuccess, showError, showConfirm } = useNotification()

  const [bindings, setBindings] = useState(null)
  const [targets, setTargets] = useState([])
  const [addOpen, setAddOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [saving, setSaving] = useState(false)
  const [deploying, setDeploying] = useState(null)
  const [chainVariants, setChainVariants] = useState([])
  const [form, setForm] = useState({
    target_id: '', cert_path: '', key_path: '', fullchain_path: '', include_root: false,
    reload_command: '', chain_variant: 'auto',
  })

  const allowed = hasPermission('read:deploy')
  const eligible = allowed && !!certificate?.id

  const load = async () => {
    try {
      setBindings(extractData(await deployService.getBindings({ certificate_id: certificate.id })) || [])
    } catch { setBindings([]) }
  }

  useEffect(() => {
    setBindings(null)
    if (eligible) load()
  }, [certificate?.id, eligible])

  // Chains a cross-certificate makes possible (#400); a binding may pin one
  useEffect(() => {
    setChainVariants([])
    if (eligible) fetchChainVariants({ type: 'certificate', id: certificate.id }).then(setChainVariants)
  }, [certificate?.id, eligible])

  if (!eligible || bindings === null) return null
  if (bindings.length === 0 && !hasPermission('write:deploy')) return null

  const openAdd = async () => {
    setEditing(null)
    try {
      const all = extractData(await deployService.getTargets()) || []
      const bound = new Set(bindings.map(b => b.target_id))
      setTargets(all.filter(target => target.enabled && !bound.has(target.id)))
    } catch { setTargets([]) }
    setForm({ target_id: '', cert_path: '', key_path: '', fullchain_path: '', include_root: false,
      reload_command: '', chain_variant: 'auto' })
    setAddOpen(true)
  }

  const openEdit = (binding) => {
    setEditing(binding)
    setForm({
      target_id: String(binding.target_id),
      cert_path: binding.cert_path || '',
      key_path: binding.key_path || '',
      fullchain_path: binding.fullchain_path || '',
      include_root: Boolean(binding.include_root),
      reload_command: binding.reload_command || '',
      chain_variant: binding.chain_variant || 'auto',
    })
    setAddOpen(true)
  }

  const handleAdd = async (e) => {
    e?.preventDefault?.()
    setSaving(true)
    try {
      const optionalPath = value => value.trim() || (editing ? null : undefined)
      const payload = {
        cert_path: optionalPath(form.cert_path),
        key_path: optionalPath(form.key_path),
        fullchain_path: optionalPath(form.fullchain_path),
        include_root: Boolean(form.fullchain_path.trim() && form.include_root),
        reload_command: form.reload_command.trim(),
        ...(form.chain_variant !== 'auto' || (editing?.chain_variant && editing.chain_variant !== 'auto')
          ? { chain_variant: form.fullchain_path.trim() ? form.chain_variant : 'auto' } : {}),
      }
      if (editing) {
        await deployService.updateBinding(editing.id, payload)
        showSuccess(t('common.updated'))
      } else {
        await deployService.createBinding({
          ...payload, certificate_id: certificate.id, target_id: Number(form.target_id),
        })
        showSuccess(t('deploy.bindingCreated'))
      }
      setAddOpen(false)
      setEditing(null)
      await load()
    } catch (err) {
      showError(err?.message || t('deploy.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleDeploy = async (binding) => {
    setDeploying(binding.id)
    try {
      await deployService.deployNow(binding.id)
      showSuccess(t('deploy.deployed', { name: binding.target_name }))
    } catch (err) {
      showError(err?.message || t('deploy.deployFailed'))
    } finally {
      setDeploying(null)
      await load()
    }
  }

  const handleDetach = async (binding) => {
    const confirmed = await showConfirm(t('deploy.detachConfirm', { name: binding.target_name }), {
      title: t('deploy.detachTarget'), variant: 'danger', confirmText: t('common.delete'),
    })
    if (!confirmed) return
    try {
      await deployService.deleteBinding(binding.id)
      await load()
    } catch (err) {
      showError(err?.message || t('deploy.deleteFailed'))
    }
  }

  const field = (key) => (e) => setForm({ ...form, [key]: e.target.value })
  const canWriteDeploy = hasPermission('write:deploy')
  const certificateName = certificate.cn || certificate.common_name || certificate.descr ||
    certificate.name || `${t('common.certificate')} #${certificate.id}`

  return (
    <>
      <CompactSection title={t('deploy.certSection')} icon={CloudArrowUp} iconClass="icon-bg-emerald">
        <div className="space-y-2">
          {bindings.length === 0 && (
            <p className="text-2xs text-text-secondary">{t('deploy.noBindings')}</p>
          )}
          {bindings.map(binding => (
            <div key={binding.id} className="p-2.5 bg-tertiary-50 border border-border rounded-lg space-y-1">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs font-medium text-text-primary truncate">{binding.target_name}</span>
                  {!binding.enabled && (
                    <Badge variant="secondary" size="sm">{t('common.disabled')}</Badge>
                  )}
                  {binding.fullchain_path && binding.include_root && (
                    <Badge variant="secondary" size="sm">{t('deploy.rootIncluded')}</Badge>
                  )}
                  {binding.fullchain_path && binding.chain_variant && binding.chain_variant !== 'auto' && (
                    <Badge variant="secondary" size="sm" data-testid="binding-variant">
                      {variantLabel(chainVariants.find(v => v.id === binding.chain_variant) || { id: binding.chain_variant, ca_name: '' }, t)}
                    </Badge>
                  )}
                  {binding.last_delivery && (
                    <Badge variant={STATUS_VARIANT[binding.last_delivery.status] || 'secondary'} size="sm"
                           title={binding.last_delivery.last_error || ''}>
                      {t(`deploy.status.${binding.last_delivery.status}`)}
                    </Badge>
                  )}
                </div>
                {canWriteDeploy && (
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Button type="button" size="xs" variant="secondary"
                            data-deploy-binding-edit="certificate"
                            onClick={() => openEdit(binding)} title={t('common.edit')}>
                      <PencilSimple size={12} />
                    </Button>
                    <Button type="button" size="xs" variant="secondary" onClick={() => handleDeploy(binding)}
                            disabled={deploying === binding.id} title={t('deploy.deployNow')}>
                      {deploying === binding.id
                        ? <ArrowsClockwise size={12} className="animate-spin" />
                        : <CloudArrowUp size={12} />}
                    </Button>
                    <Button type="button" size="xs" variant="danger" onClick={() => handleDetach(binding)}>
                      <Trash size={12} />
                    </Button>
                  </div>
                )}
              </div>
              <p className="text-2xs text-text-tertiary font-mono truncate">
                {[binding.cert_path, binding.key_path, binding.fullchain_path].filter(Boolean).join(' · ')}
              </p>
              {binding.reload_command && (
                <p className="text-2xs text-text-tertiary font-mono truncate"
                   title={binding.reload_command}>
                  {t('deploy.reloadCommand')}: {binding.reload_command}
                </p>
              )}
              {binding.last_delivery?.delivered_at && (
                <p className="text-2xs text-text-tertiary">
                  {t('deploy.lastDeployed', { date: formatDate(binding.last_delivery.delivered_at) })}
                </p>
              )}
              {binding.last_delivery?.status === 'failed' && binding.last_delivery.last_error && (
                <p className="text-2xs status-danger-text truncate" title={binding.last_delivery.last_error}>
                  {binding.last_delivery.last_error}
                </p>
              )}
            </div>
          ))}
          {canWriteDeploy && (
            <Button type="button" size="xs" variant="secondary" onClick={openAdd}>
              <Plus size={12} /> {t('deploy.attachTarget')}
            </Button>
          )}
        </div>
      </CompactSection>

      <Modal open={addOpen} onOpenChange={(v) => {
               if (!v && !saving) { setAddOpen(false); setEditing(null) }
             }}
             title={editing
               ? t('deploy.editDeploymentFor', { name: certificateName })
               : t('deploy.attachTargetFor', { name: certificateName })} size="md">
        <form onSubmit={handleAdd} className="p-4 space-y-3">
          <div className="space-y-1">
            <label className="block text-xs font-medium text-text-secondary">{t('deploy.target')}</label>
            <select className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-md text-sm text-text-primary focus:outline-none focus:border-accent-primary"
                    value={form.target_id} onChange={field('target_id')} required disabled={Boolean(editing)}>
              {editing ? (
                <option value={editing.target_id}>{editing.target_name} ({editing.target_host})</option>
              ) : (
                <>
                  <option value="" disabled>{t('deploy.selectTarget')}</option>
                  {targets.map(target => (
                    <option key={target.id} value={target.id}>
                      {target.name} ({target.username}@{target.host})
                    </option>
                  ))}
                </>
              )}
            </select>
            {!editing && targets.length === 0 && (
              <p className="text-2xs text-text-tertiary">{t('deploy.noAvailableTargets')}</p>
            )}
          </div>
          <div className="space-y-1">
            <label className="block text-xs font-medium text-text-secondary">{t('deploy.certPath')}</label>
            <input className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-md text-sm font-mono text-text-primary focus:outline-none focus:border-accent-primary"
                   placeholder="/etc/ssl/certs/app.pem" value={form.cert_path} onChange={field('cert_path')} />
          </div>
          <div className="space-y-1">
            <label className="block text-xs font-medium text-text-secondary">{t('deploy.keyPath')}</label>
            <input className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-md text-sm font-mono text-text-primary focus:outline-none focus:border-accent-primary"
                   placeholder="/etc/ssl/private/app.key" value={form.key_path} onChange={field('key_path')}
                   disabled={!certificate.has_private_key} />
            {!certificate.has_private_key && (
              <p className="text-2xs text-text-tertiary">{t('deploy.noKeyInUcm')}</p>
            )}
          </div>
          <div className="space-y-1">
            <label className="block text-xs font-medium text-text-secondary">{t('deploy.fullchainPath')}</label>
            <input className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-md text-sm font-mono text-text-primary focus:outline-none focus:border-accent-primary"
                   placeholder="/etc/ssl/certs/app-fullchain.pem" value={form.fullchain_path} onChange={field('fullchain_path')} />
          </div>
          {form.fullchain_path.trim() && (
            <label className="flex items-start gap-3 p-3 bg-bg-tertiary border border-border rounded-md cursor-pointer">
              <input type="checkbox" className="mt-0.5 w-4 h-4 accent-accent-primary"
                     checked={form.include_root}
                     onChange={(e) => setForm({ ...form, include_root: e.target.checked })} />
              <div>
                <div className="text-sm text-text-primary">{t('export.includeRoot')}</div>
                <div className="text-xs text-text-tertiary">{t('export.includeRootDesc')}</div>
              </div>
            </label>
          )}
          {form.fullchain_path.trim() && chainVariants.length > 1 && (
            <div className="space-y-1">
              <label htmlFor="deploy-chain-variant" className="block text-xs font-medium text-text-secondary">
                {t('chainVariant.label')}
              </label>
              <ChainVariantSelect id="deploy-chain-variant" variants={chainVariants} disableUnservable
                                  value={form.chain_variant}
                                  onChange={(value) => setForm({ ...form, chain_variant: value })} />
              <p className="text-2xs text-text-tertiary">{t('chainVariant.deployHint')}</p>
            </div>
          )}
          <div className="space-y-1">
            <label className="block text-xs font-medium text-text-secondary">
              {t('deploy.reloadCommand')}
            </label>
            <input className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-md text-sm font-mono text-text-primary focus:outline-none focus:border-accent-primary"
                   placeholder="/usr/sbin/nginx -t && /usr/sbin/nginx -s reload"
                   value={form.reload_command} onChange={field('reload_command')} maxLength={512} />
            <p className="text-2xs text-text-tertiary">{t('deploy.reloadCommandHint')}</p>
          </div>
          <p className="text-2xs text-text-tertiary">{t('deploy.pathsHint')}</p>
          <div className="flex justify-end gap-2 pt-3 border-t border-border">
            <Button type="button" variant="secondary"
                    onClick={() => { setAddOpen(false); setEditing(null) }} disabled={saving}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" variant="primary" loading={saving}
                    disabled={!form.target_id || !(form.cert_path.trim() || form.key_path.trim() || form.fullchain_path.trim())}>
              {editing ? t('common.save') : t('deploy.attach')}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  )
}
