/**
 * DeploySection — deploy targets management (#299, admin-only).
 *
 * A deploy target contains only the reusable SSH/SFTP connection. Files,
 * paths and optional reload commands belong to certificate/CRL bindings.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CloudArrowUp, Plus, TestTube, PencilSimple, Trash, ArrowsClockwise, Copy, Check } from '@phosphor-icons/react'
import { Button, Badge, HelpCard, DetailSection, DetailContent, DetailHeader, EmptyState } from '../../components'
import { Modal } from '../../components/Modal'
import { deployService } from '../../services'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks/useClipboard'
import { extractData, formatDate } from '../../lib/utils'
import { useFipsMode } from '../../lib/policyAlgorithms'

const EMPTY_FORM = {
  name: '', host: '', port: 22, username: '', private_key: '', enabled: true,
}

export default function DeploySection() {
  const { t } = useTranslation()
  const fips = useFipsMode()
  const { showSuccess, showError, showConfirm } = useNotification()

  const [targets, setTargets] = useState([])
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [publicKeyFor, setPublicKeyFor] = useState(null)
  const { copy, isCopied } = useClipboard(1500)

  const load = async () => {
    try {
      setTargets(extractData(await deployService.getTargets()) || [])
    } catch (err) {
      showError(err?.message || t('deploy.loadFailed'))
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setFormOpen(true)
  }

  const openEdit = (target) => {
    setEditing(target)
    setForm({
      name: target.name, host: target.host, port: target.port,
      username: target.username, private_key: '', enabled: target.enabled,
    })
    setFormOpen(true)
  }

  const handleSubmit = async (e) => {
    e?.preventDefault?.()
    setSaving(true)
    try {
      const payload = {
        name: form.name.trim(), host: form.host.trim(),
        port: Number(form.port) || 22, username: form.username.trim(),
        enabled: form.enabled,
      }
      if (form.private_key.trim()) payload.private_key = form.private_key
      if (editing) {
        await deployService.updateTarget(editing.id, payload)
        showSuccess(t('deploy.targetUpdated'))
      } else {
        const created = extractData(await deployService.createTarget(payload))
        showSuccess(t('deploy.targetCreated'))
        if (created?.public_key && !form.private_key.trim()) setPublicKeyFor(created)
      }
      setFormOpen(false)
      await load()
    } catch (err) {
      showError(err?.message || t('deploy.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async (target) => {
    setTesting(target.id)
    try {
      const result = extractData(await deployService.testTarget(target.id))
      showSuccess(t('deploy.testOk', { fingerprint: result?.host_key_fingerprint || '?' }))
      await load()
    } catch (err) {
      showError(err?.message || t('deploy.testFailed'))
    } finally {
      setTesting(null)
    }
  }

  const handleResetHostKey = async () => {
    if (!editing) return
    const confirmed = await showConfirm(t('deploy.resetHostKeyConfirm', { name: editing.name }), {
      title: t('deploy.resetHostKey'), variant: 'danger', confirmText: t('deploy.resetHostKey'),
    })
    if (!confirmed) return
    try {
      await deployService.updateTarget(editing.id, { reset_host_key: true })
      showSuccess(t('deploy.hostKeyReset'))
      setFormOpen(false)
      await load()
    } catch (err) {
      showError(err?.message || t('deploy.saveFailed'))
    }
  }

  const handleDelete = async (target) => {
    const confirmed = await showConfirm(t('deploy.deleteConfirm', { name: target.name }), {
      title: t('deploy.deleteTarget'), variant: 'danger', confirmText: t('common.delete'),
    })
    if (!confirmed) return
    try {
      await deployService.deleteTarget(target.id)
      showSuccess(t('deploy.targetDeleted'))
      await load()
    } catch (err) {
      showError(err?.message || t('deploy.deleteFailed'))
    }
  }

  const copyPublicKey = () => copy(publicKeyFor?.public_key || '')

  const field = (key) => (e) => setForm({ ...form, [key]: e.target.value })
  const applySameHostPreset = () => setForm(current => ({
    ...current,
    host: '127.0.0.1',
    username: 'ucm-deploy',
  }))

  return (
    <DetailContent>
      <DetailHeader
        icon={CloudArrowUp}
        title={t('deploy.title')}
        subtitle={t('deploy.subtitle')}
      />

      <HelpCard variant="info" title={t('deploy.helpTitle')} className="mb-4">
        {t('deploy.helpDescription')}
      </HelpCard>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-6 h-6 border-2 border-accent-primary-op30 border-t-accent-primary rounded-full animate-spin" />
        </div>
      ) : targets.length === 0 ? (
        <EmptyState
          icon={CloudArrowUp}
          title={t('deploy.noTargets')}
          description={t('deploy.noTargetsDescription')}
          action={{ label: t('deploy.addTarget'), onClick: openCreate }}
        />
      ) : (
        <DetailSection title={t('deploy.targets')} icon={CloudArrowUp} iconClass="icon-bg-emerald">
          <div className="space-y-3">
            {targets.map(target => (
              <div key={target.id} className="flex items-center justify-between p-4 bg-tertiary-50 border border-border rounded-lg">
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <div className="w-10 h-10 rounded-lg bg-accent-primary-op10 flex items-center justify-center flex-shrink-0">
                    <CloudArrowUp size={20} className="text-accent-primary" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-text-primary truncate">{target.name}</span>
                      <Badge variant={target.enabled ? 'success' : 'secondary'} size="sm">
                        {target.enabled ? t('common.enabled') : t('common.disabled')}
                      </Badge>
                      {target.failure_count > 0 && (
                        <Badge variant="danger" size="sm">{t('deploy.failures', { count: target.failure_count })}</Badge>
                      )}
                    </div>
                    <p className="text-xs text-text-secondary truncate font-mono">
                      {target.username}@{target.host}:{target.port}
                    </p>
                    <p className="text-2xs text-text-tertiary truncate">
                      {target.host_key_pinned
                        ? t('deploy.hostKeyPinned', { fingerprint: target.host_key_fingerprint })
                        : t('deploy.hostKeyNotPinned')}
                      {target.last_success_at && ` · ${t('deploy.lastSuccess', { date: formatDate(target.last_success_at) })}`}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                  <Button type="button" size="sm" variant="secondary" onClick={() => setPublicKeyFor(target)} title={t('deploy.showPublicKey')}>
                    <Copy size={14} />
                  </Button>
                  <Button type="button" size="sm" variant="secondary" onClick={() => handleTest(target)} disabled={testing === target.id} title={t('deploy.testConnection')}>
                    {testing === target.id ? <ArrowsClockwise size={14} className="animate-spin" /> : <TestTube size={14} />}
                  </Button>
                  <Button type="button" size="sm" variant="secondary" onClick={() => openEdit(target)}>
                    <PencilSimple size={14} />
                  </Button>
                  <Button type="button" size="sm" variant="danger" onClick={() => handleDelete(target)}>
                    <Trash size={14} />
                  </Button>
                </div>
              </div>
            ))}
            <Button type="button" variant="secondary" onClick={openCreate}>
              <Plus size={16} /> {t('deploy.addTarget')}
            </Button>
          </div>
        </DetailSection>
      )}

      {/* Create / edit modal */}
      <Modal open={formOpen} onOpenChange={(v) => !v && !saving && setFormOpen(false)}
             title={editing ? t('deploy.editTarget') : t('deploy.addTarget')} size="md">
        <form onSubmit={handleSubmit} className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="block text-xs font-medium text-text-secondary">{t('common.name')}</label>
              <input className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-md text-sm text-text-primary focus:outline-none focus:border-accent-primary"
                     value={form.name} onChange={field('name')} required maxLength={120} />
            </div>
            <div className="space-y-1">
              <label className="block text-xs font-medium text-text-secondary">{t('deploy.sshUser')}</label>
              <input className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-md text-sm text-text-primary focus:outline-none focus:border-accent-primary"
                     value={form.username} onChange={field('username')} required maxLength={120} />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1 col-span-2">
              <label className="block text-xs font-medium text-text-secondary">{t('deploy.host')}</label>
              <input className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-md text-sm text-text-primary font-mono focus:outline-none focus:border-accent-primary"
                     value={form.host} onChange={field('host')} required maxLength={255} />
              <div className="flex items-start gap-2 text-2xs">
                <button
                  type="button"
                  className="text-accent-primary hover:underline whitespace-nowrap"
                  onClick={applySameHostPreset}
                >
                  {t('deploy.sameHost')}
                </button>
                <span className="text-text-tertiary">{t('deploy.sameHostHint')}</span>
              </div>
            </div>
            <div className="space-y-1">
              <label className="block text-xs font-medium text-text-secondary">{t('deploy.port')}</label>
              <input type="number" min={1} max={65535}
                     className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-md text-sm text-text-primary focus:outline-none focus:border-accent-primary"
                     value={form.port} onChange={field('port')} />
            </div>
          </div>
          <div className="space-y-1">
            <label className="block text-xs font-medium text-text-secondary">
              {editing ? t('deploy.privateKeyRotate') : t(fips ? 'deploy.privateKeyOptionalFips' : 'deploy.privateKeyOptional')}
            </label>
            <textarea className="w-full h-20 px-3 py-2 bg-bg-tertiary border border-border rounded-md text-xs font-mono text-text-primary resize-y focus:outline-none focus:border-accent-primary"
                      placeholder={t('deploy.privateKeyPlaceholder')}
                      value={form.private_key} onChange={field('private_key')} spellCheck={false} />
          </div>
          {editing && (
            <label className="flex items-center gap-2 text-sm text-text-primary">
              <input type="checkbox" checked={form.enabled}
                     onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
              {t('common.enabled')}
            </label>
          )}
          <div className="flex items-center justify-between gap-2 pt-3 border-t border-border">
            <div>
              {editing?.host_key_pinned && (
                <Button type="button" size="sm" variant="danger" onClick={handleResetHostKey} disabled={saving}>
                  {t('deploy.resetHostKey')}
                </Button>
              )}
            </div>
            <div className="flex gap-2">
              <Button type="button" variant="secondary" onClick={() => setFormOpen(false)} disabled={saving}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" variant="primary" loading={saving}>
                {editing ? t('common.save') : t('common.create')}
              </Button>
            </div>
          </div>
        </form>
      </Modal>

      {/* Public key modal — install on the target's authorized_keys */}
      <Modal open={!!publicKeyFor} onOpenChange={(v) => !v && setPublicKeyFor(null)}
             title={t('deploy.publicKeyTitle')} size="md">
        <div className="p-4 space-y-3">
          <p className="text-xs text-text-secondary">{t('deploy.publicKeyHint', { username: publicKeyFor?.username || '' })}</p>
          <pre className="p-3 bg-bg-tertiary border border-border rounded-md text-2xs font-mono text-text-primary whitespace-pre-wrap break-all">
            {publicKeyFor?.public_key || t('deploy.publicKeyUnavailable')}
          </pre>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={copyPublicKey} disabled={!publicKeyFor?.public_key}>
              {isCopied() ? <Check size={14} /> : <Copy size={14} />} {t('common.copy')}
            </Button>
            <Button type="button" variant="primary" onClick={() => setPublicKeyFor(null)}>
              {t('common.close')}
            </Button>
          </div>
        </div>
      </Modal>
    </DetailContent>
  )
}
