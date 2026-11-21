/**
 * The certificate's deployments (#299), a section of the inspector's « Plus de détails » drawn with
 * the mockup's detail vocabulary (section title, record rows, badges, buttons): each binding's target,
 * paths and last delivery, and to who may write them, attach a target, deploy now, edit or detach.
 * An HTTP target (#428) takes no paths: its body template decides what is sent.
 * Renders nothing without the right to read deployments.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Btn, Icon, IconBtn, Pill, RecordList, RecordRow } from '../atelier'
import { ChainVariantSelect, variantLabel } from '../ChainVariantSelect'
import { fetchChainVariants } from '../../lib/crossCertificates'
import { deployService } from '../../services'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks'
import { extractData, formatDate } from '../../lib/utils'

const STATUS_TONE = { delivered: 'good', pending: 'warn', failed: 'bad' }

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
  const [reattaching, setReattaching] = useState(null)
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

  // The work queue links to a binding with ?binding=<id>: that row is marked and brought into view
  const focusId = Number(new URLSearchParams(window.location.search).get('binding')) || null
  useEffect(() => {
    if (focusId && bindings?.length) document.querySelector(`[data-binding-id="${focusId}"]`)?.scrollIntoView?.({ block: 'nearest' })
  }, [focusId, bindings])

  if (!eligible || bindings === null) return null
  if (bindings.length === 0 && !hasPermission('write:deploy')) return null

  const selectedTarget = editing
    ? { kind: editing.target_kind, allow_private_key: false }
    : targets.find(target => String(target.id) === String(form.target_id))
  const httpTarget = selectedTarget?.kind === 'http'
  const hasPath = Boolean(form.cert_path.trim() || form.key_path.trim() || form.fullchain_path.trim())

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
      const chainWanted = httpTarget || Boolean(form.fullchain_path.trim())
      const payload = httpTarget ? {
        include_root: Boolean(form.include_root),
      } : {
        cert_path: optionalPath(form.cert_path),
        key_path: optionalPath(form.key_path),
        fullchain_path: optionalPath(form.fullchain_path),
        include_root: Boolean(form.fullchain_path.trim() && form.include_root),
        reload_command: form.reload_command.trim(),
      }
      if (form.chain_variant !== 'auto' || (editing?.chain_variant && editing.chain_variant !== 'auto')) {
        payload.chain_variant = chainWanted ? form.chain_variant : 'auto'
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

  const handleReattach = async (binding) => {
    setReattaching(binding.id)
    try {
      await deployService.reattachBinding(binding.id)
      showSuccess(t('deploy.reattached', { name: binding.target_name }))
    } catch (err) {
      showError(err?.message || t('deploy.reattachFailed'))
    } finally {
      setReattaching(null)
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

  const pathsOf = (binding) => (binding.target_kind === 'http'
    ? t('deploy.httpBinding')
    : <span className="mono">{[binding.cert_path, binding.key_path, binding.fullchain_path].filter(Boolean).join(' · ')}</span>)

  return (
    <>
      <section data-testid="cert-deploy">
        <h3 className="section-title">{t('deploy.certSection')}</h3>
        <RecordList empty={t('deploy.noBindings')} label={t('deploy.certSection')}>
          {bindings.map(binding => {
            const attention = binding.needs_attention
            const delivery = binding.last_delivery
            return (
              <RecordRow key={binding.id} data-binding-id={binding.id} aria-current={binding.id === focusId ? 'true' : undefined}
                title={binding.target_name}
                meta={(
                  <>
                    {pathsOf(binding)}
                    {binding.reload_command && <> · {t('deploy.reloadCommand')}: <span className="mono" title={binding.reload_command}>{binding.reload_command}</span></>}
                    {delivery?.delivered_at && <> · {t('deploy.lastDeployed', { date: formatDate(delivery.delivered_at) })}</>}
                  </>
                )}
                badge={(
                  <>
                    {!binding.enabled && <Pill tone="muted" icon="block" label={t('common.disabled')} />}
                    {binding.fullchain_path && binding.include_root && <Pill icon="shield" label={t('deploy.rootIncluded')} />}
                    {binding.fullchain_path && binding.chain_variant && binding.chain_variant !== 'auto' && (
                      <span className="badge" data-testid="binding-variant"><Icon name="link" />
                        {variantLabel(chainVariants.find(v => v.id === binding.chain_variant) || { id: binding.chain_variant, ca_name: '' }, t)}
                      </span>
                    )}
                    {attention && <Pill tone="bad" label={t('deploy.leftBehind')} />}
                    {delivery && <Pill tone={STATUS_TONE[delivery.status]} label={t(`deploy.status.${delivery.status}`)} />}
                  </>
                )}
                action={canWriteDeploy && (
                  <>
                    <Btn icon="send" write data-deploy-now={binding.id} disabled={deploying === binding.id || undefined}
                      aria-busy={deploying === binding.id || undefined} onClick={() => handleDeploy(binding)}>{t('deploy.deployNow')}</Btn>
                    <IconBtn quiet icon="settings" label={t('common.edit')} data-deploy-binding-edit="certificate" onClick={() => openEdit(binding)} />
                    <IconBtn quiet icon="close" label={t('deploy.detachTarget')} write data-deploy-detach={binding.id} onClick={() => handleDetach(binding)} />
                  </>
                )}
                extra={(
                  <>
                    {attention && (
                      <div data-testid="binding-left-behind">
                        <p className="rl-error"><Icon name="warning" /><span>{t('deploy.leftBehindHelp')}</span></p>
                        {!attention.can_reattach && (
                          <span className="rl-meta">
                            {attention.successor_archived
                              ? t('deploy.leftBehindSuperseded')
                              : attention.successor_has_key ? t('deploy.leftBehindTargetTaken') : t('deploy.leftBehindNoKey')}
                          </span>
                        )}
                        {(attention.successor_id || (canWriteDeploy && attention.can_reattach)) && (
                          <div className="rl-action">
                            {attention.successor_id && (
                              <a className="text-link" href={`/certificates/${attention.successor_id}`}>{t('deploy.openRenewed')}</a>
                            )}
                            {canWriteDeploy && attention.can_reattach && (
                              <Btn icon="link" write data-deploy-reattach={binding.id} disabled={reattaching === binding.id || undefined}
                                aria-busy={reattaching === binding.id || undefined} onClick={() => handleReattach(binding)}>{t('deploy.reattach')}</Btn>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                    {delivery?.status === 'failed' && delivery.last_error && (
                      <p className="rl-error"><Icon name="warning" /><span>{delivery.last_error}</span></p>
                    )}
                  </>
                )} />
            )
          })}
        </RecordList>
        {canWriteDeploy && (
          <div className="rl-action">
            <Btn icon="plus" data-action="attach-target" onClick={openAdd}>{t('deploy.attachTarget')}</Btn>
          </div>
        )}
      </section>

      {addOpen && (
        <AtelierDialog onClose={() => { if (!saving) { setAddOpen(false); setEditing(null) } }} testId="deploy-attach-dialog"
          title={editing ? t('deploy.editDeploymentFor', { name: certificateName }) : t('deploy.attachTargetFor', { name: certificateName })}>
          <form onSubmit={handleAdd}>
            <div className="form-fields">
              <div className="field full">
                <label htmlFor="deploy-target">{t('deploy.target')}</label>
                <select id="deploy-target" value={form.target_id} onChange={field('target_id')} required disabled={Boolean(editing)}
                  aria-describedby={!editing && targets.length === 0 ? 'hint-deploy-target' : undefined}>
                  {editing ? (
                    <option value={editing.target_id}>{editing.target_name} ({editing.target_host})</option>
                  ) : (
                    <>
                      <option value="" disabled>{t('deploy.selectTarget')}</option>
                      {targets.map(target => (
                        <option key={target.id} value={target.id}>
                          {target.name} ({target.kind === 'http' ? `${target.http_method} ${target.url}` : `${target.username}@${target.host}`})
                        </option>
                      ))}
                    </>
                  )}
                </select>
                {!editing && targets.length === 0 && <small id="hint-deploy-target">{t('deploy.noAvailableTargets')}</small>}
              </div>
              {httpTarget && (
                <p className="notice">
                  <Icon name="help" />
                  <span>
                    {t('deploy.httpBindingHint', { chainVariable: '{{chain_pem}}', fullchainVariable: '{{fullchain_pem}}' })}
                    {selectedTarget?.allow_private_key && ` ${t('deploy.httpBindingKeyHint')}`}
                  </span>
                </p>
              )}
              {!httpTarget && (<>
                <div className="field full">
                  <label htmlFor="deploy-cert-path">{t('deploy.certPath')}</label>
                  <input id="deploy-cert-path" className="mono" autoComplete="off" spellCheck={false} placeholder="/etc/ssl/certs/app.pem" value={form.cert_path} onChange={field('cert_path')} />
                </div>
                <div className="field full">
                  <label htmlFor="deploy-key-path">{t('deploy.keyPath')}</label>
                  <input id="deploy-key-path" className="mono" autoComplete="off" spellCheck={false} placeholder="/etc/ssl/private/app.key" value={form.key_path} onChange={field('key_path')}
                    disabled={!certificate.has_private_key} aria-describedby={!certificate.has_private_key ? 'hint-deploy-key-path' : undefined} />
                  {!certificate.has_private_key && <small id="hint-deploy-key-path">{t('deploy.noKeyInUcm')}</small>}
                </div>
                <div className="field full">
                  <label htmlFor="deploy-fullchain-path">{t('deploy.fullchainPath')}</label>
                  <input id="deploy-fullchain-path" className="mono" autoComplete="off" spellCheck={false} placeholder="/etc/ssl/certs/app-fullchain.pem" value={form.fullchain_path} onChange={field('fullchain_path')} />
                </div>
              </>)}
              {(httpTarget || form.fullchain_path.trim()) && (
                <div className="field full">
                  <label className="checkbox-line">
                    <input type="checkbox" checked={form.include_root} aria-describedby="hint-deploy-root"
                      onChange={(e) => setForm({ ...form, include_root: e.target.checked })} />
                    {t('export.includeRoot')}
                  </label>
                  <small id="hint-deploy-root">{t('export.includeRootDesc')}</small>
                </div>
              )}
              {(httpTarget || form.fullchain_path.trim()) && chainVariants.length > 1 && (
                <div className="field full">
                  <label htmlFor="deploy-chain-variant">{t('chainVariant.label')}</label>
                  <ChainVariantSelect id="deploy-chain-variant" variants={chainVariants} disableUnservable
                    value={form.chain_variant} onChange={(value) => setForm({ ...form, chain_variant: value })} />
                  <small>{t('chainVariant.deployHint')}</small>
                </div>
              )}
              {!httpTarget && (
                <div className="field full">
                  <label htmlFor="deploy-reload">{t('deploy.reloadCommand')}</label>
                  <input id="deploy-reload" className="mono" autoComplete="off" spellCheck={false} placeholder="/usr/sbin/nginx -t && /usr/sbin/nginx -s reload"
                    value={form.reload_command} onChange={field('reload_command')} maxLength={512} aria-describedby="hint-deploy-reload" />
                  <small id="hint-deploy-reload">{t('deploy.reloadCommandHint')}</small>
                </div>
              )}
            </div>
            {!httpTarget && <p className="small muted" style={{ marginTop: 16 }}>{t('deploy.pathsHint')}</p>}
            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => { setAddOpen(false); setEditing(null) }} disabled={saving || undefined}>{t('common.cancel')}</button>
              <button type="submit" className="btn primary" disabled={saving || !form.target_id || !(httpTarget || hasPath) || undefined}>
                {saving ? t('common.loading') : editing ? t('common.save') : t('deploy.attach')}
              </button>
            </div>
          </form>
        </AtelierDialog>
      )}
    </>
  )
}
