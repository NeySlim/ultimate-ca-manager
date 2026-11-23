/**
 * DeploySection — deploy targets management (#299, admin-only).
 *
 * A deploy target contains only the reusable connection: SSH/SFTP, or an
 * HTTP API with its body template (#428). Files, paths and optional reload
 * commands belong to certificate/CRL bindings.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, ListView, Toolbar, SearchField, NoMatch, Pill, EmptyBlock, useClientList, useSortParam } from '../../components/atelier'
import { Modal, Input, NumberInput, Select, Textarea, ToggleSwitch, ChoiceField, Notice } from '../../components/atelier/Form'
import { deployService } from '../../services'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks/useClipboard'
import { extractData, formatDate } from '../../lib/utils'
import { useFipsMode } from '../../lib/policyAlgorithms'

const EMPTY_FORM = {
  kind: 'ssh', name: '', host: '', port: 22, username: '', private_key: '', enabled: true,
  url: '', http_method: 'POST', http_headers: '', body_template: '', tls_ca_pem: '', allow_private_key: false,
  clear_headers: false,
}

const HTTP_TEMPLATE_VARIABLES = [
  'cert_pem', 'key_pem', 'chain_pem', 'fullchain_pem', 'name', 'cn', 'san_dns', 'serial', 'serial_hex',
  'not_before', 'not_after', 'fingerprint_sha256', 'refid', 'certificate_id', 'event',
]
// Literal template syntax passed as values: a {{ }} inside a locale string would be interpolated
const TEMPLATE_HINT_VARS = {
  example: '{{name}}', jsonExample: '{{cert_pem|json}}', jsonstrExample: '{{cn|jsonstr}}', b64Example: '{{cert_pem|b64}}', urlExample: '{{cn|urlencode}}',
}
// The targets by name
const BY_NAME = { key: 'name', asc: true }
const SORT_KEYS = ['name', 'kind', 'connection', 'success', 'state']
const HTTP_TEMPLATE_EXAMPLE = '{"name": {{name|json}}, "cert": {{cert_pem|json}}, "chain": {{chain_pem|json}}}'

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
  const [search, setSearch] = useState('')
  // The search reads the name, the host and the address; the sort is in the address under this list's scope
  const needle = search.trim().toLowerCase()
  const shownTargets = needle
    ? targets.filter((target) => [target.name, target.host, target.url, target.username].some((v) => (v || '').toLowerCase().includes(needle)))
    : targets
  const sortParam = useSortParam(BY_NAME, SORT_KEYS, { scope: 'deploy' })
  const targetList = useClientList(shownTargets, {
    sortParam,
    resetKey: needle,
    sorts: {
      name: (r) => r.name, kind: (r) => r.kind || 'ssh', connection: (r) => (r.kind === 'http' ? r.url : r.host),
      success: (r) => (r.last_success_at ? Date.parse(r.last_success_at) : null), state: (r) => (r.enabled ? 0 : 1),
    },
  })

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
      ...EMPTY_FORM,
      kind: target.kind || 'ssh', name: target.name, host: target.host, port: target.port,
      username: target.username, private_key: '', enabled: target.enabled,
      url: target.url || '', http_method: target.http_method || 'POST', http_headers: '',
      body_template: target.body_template || '', tls_ca_pem: target.tls_ca_pem || '',
      allow_private_key: Boolean(target.allow_private_key),
    })
    setFormOpen(true)
  }

  const isHttp = form.kind === 'http'

  const httpPayload = () => {
    const payload = {
      name: form.name.trim(), url: form.url.trim(), http_method: form.http_method,
      body_template: form.body_template, tls_ca_pem: form.tls_ca_pem.trim(),
      allow_private_key: form.allow_private_key, enabled: form.enabled,
    }
    // Header values are never read back: an empty box keeps the stored ones, {} removes them
    if (form.http_headers.trim()) payload.http_headers = form.http_headers
    else if (form.clear_headers) payload.http_headers = {}
    if (!editing) payload.kind = 'http'
    return payload
  }

  const handleSubmit = async (e) => {
    e?.preventDefault?.()
    setSaving(true)
    try {
      const payload = isHttp ? httpPayload() : {
        name: form.name.trim(), host: form.host.trim(),
        port: Number(form.port) || 22, username: form.username.trim(),
        enabled: form.enabled,
      }
      if (!isHttp && form.private_key.trim()) payload.private_key = form.private_key
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
      showSuccess(target.kind === 'http'
        ? t('deploy.testOkHttp', { status: result?.status_code ?? '?' })
        : t('deploy.testOk', { fingerprint: result?.host_key_fingerprint || '?' }))
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
  const clearHeaders = () => setForm({ ...form, http_headers: '', clear_headers: false })
  const removeStoredHeaders = () => setForm({ ...form, http_headers: '', clear_headers: true })
  const applySameHostPreset = () => setForm(current => ({
    ...current,
    host: '127.0.0.1',
    username: 'ucm-deploy',
  }))

  const closeForm = () => { if (!saving) setFormOpen(false) }
  // The module list of the Active Directory section: the name opens the form, the row holds the actions
  const connection = (target) => (target.kind === 'http' ? `${target.http_method} ${target.url}` : `${target.username}@${target.host}:${target.port}`)
  const delivery = (target) => (target.kind === 'http'
    ? (target.allow_private_key ? t('deploy.httpSendsKey') : t('deploy.httpCertOnly'))
    : target.host_key_pinned
      ? t('deploy.hostKeyPinned', { fingerprint: target.host_key_fingerprint })
      : t('deploy.hostKeyNotPinned'))
  const rowActions = (target) => [
    ...(target.kind !== 'http' ? [{ icon: 'key', label: t('deploy.showPublicKey'), onClick: () => setPublicKeyFor(target) }] : []),
    { icon: 'send', label: t('deploy.testConnection'), disabled: testing === target.id, onClick: () => handleTest(target) },
    { icon: 'settings', label: t('common.edit'), onClick: () => openEdit(target) },
    { icon: 'close', label: t('common.delete'), write: true, onClick: () => handleDelete(target) },
  ]
  const empty = (
    <EmptyBlock id="deploy" icon="upload" title={t('deploy.noTargets')} text={t('deploy.noTargetsDescription')}
      action={{ label: t('deploy.addTarget'), icon: 'plus', onClick: openCreate, primary: true }} />
  )
  // Without any target the section keeps its empty block alone, the table comes with the first one
  const list = !loading && targets.length === 0 ? empty : (
    <>
      <ListView label={t('deploy.targets')} icon="upload" list={targetList} nameSort="name" loading={loading} scrollId="deploy-scroll" cardActions
        title={(target) => target.name}
        status={(target) => (
          <span className="row-actions">
            <Pill tone={target.enabled ? 'good' : 'muted'} label={target.enabled ? t('common.enabled') : t('common.disabled')} />
            {target.failure_count > 0 && <Pill tone="bad" label={t('deploy.failures', { count: target.failure_count })} />}
          </span>
        )}
        onOpen={openEdit}
        toolbar={(
          <Toolbar>
            <SearchField id="deploy-search" label={t('common.search')} placeholder={t('deploy.searchPlaceholder')} value={search} onChange={setSearch} />
          </Toolbar>
        )}
        columns={[
          { id: 'kind', label: t('deploy.kindColumn'), cell: (target) => <Pill icon={target.kind === 'http' ? 'globe' : 'terminal'} label={t(`deploy.kind_${target.kind === 'http' ? 'http' : 'ssh'}`)} />,
            kind: 'fit', priority: 3, sort: 'kind' },
          { id: 'connection', label: t('deploy.connectionColumn'), cell: (target) => <span className="mono">{connection(target)}</span>, title: connection,
            kind: 'text', priority: 2, grow: true, sort: 'connection' },
          { id: 'delivery', label: t('deploy.deliveryColumn'), cell: delivery, title: delivery, kind: 'text', priority: 4 },
          { id: 'success', label: t('deploy.lastSuccessColumn'), cell: (target) => (target.last_success_at ? formatDate(target.last_success_at) : '—'),
            kind: 'fit', priority: 3, sort: 'success' },
          { status: true, sort: 'state' },
        ]}
        rowActions={rowActions}
        empty={<NoMatch title={t('common.noResults')} resetLabel={t('common.clear')} onReset={() => setSearch('')} />}
        footer={targetList.paged ? { range: t('table.range', { start: targetList.start, end: targetList.end, total: targetList.total }) } : undefined} />
      {targets.length > 0 && (
        <div className="settings-actions">
          <Btn tone="primary" icon="plus" onClick={openCreate}>{t('deploy.addTarget')}</Btn>
        </div>
      )}
    </>
  )

  return (
    <>
      <Notice><strong>{t('deploy.helpTitle')}</strong>{' '}{t('deploy.helpDescription')}</Notice>
      {list}

      {/* Create / edit: the mockup's dialog form */}
      <Modal open={formOpen} onClose={closeForm} title={editing ? t('deploy.editTarget') : t('deploy.addTarget')}>
        <form onSubmit={handleSubmit}>
          <div className="form-fields">
            {!editing && (
              <ChoiceField name="deploy-kind" legend={t('deploy.kind')} value={form.kind} onChange={(kind) => setForm({ ...form, kind })}
                options={['ssh', 'http'].map(kind => ({ value: kind, label: t(`deploy.kind_${kind}`), hint: t(`deploy.kind_${kind}Hint`) }))} />
            )}
            <Input id="deploy-name" label={t('common.name')} value={form.name} onChange={field('name')} required maxLength={120} data-autofocus="" />
            {!isHttp && (
              <Input id="deploy-user" label={t('deploy.sshUser')} value={form.username} onChange={field('username')} required maxLength={120} />
            )}
            {isHttp && (
              <>
                <Select id="deploy-method" label={t('deploy.httpMethod')} value={form.http_method} onChange={(v) => setForm({ ...form, http_method: v })}
                  options={['POST', 'PUT', 'PATCH'].map(m => ({ value: m, label: m }))} />
                <Input id="deploy-url" full mono label={t('deploy.httpUrl')} type="url" placeholder="https://firewall.example.net/api/trust/cert/add"
                  value={form.url} onChange={field('url')} required maxLength={2048} />
                <Textarea id="deploy-headers" mono rows={3} spellCheck={false}
                  label={editing ? t('deploy.httpHeadersRotate', { count: editing.http_header_names?.length || 0 }) : t('deploy.httpHeaders')}
                  placeholder={'Authorization: Bearer ...\nX-Api-Key: ...'} value={form.http_headers} onChange={field('http_headers')}
                  hint={editing?.http_header_names?.length > 0 ? (
                    <>
                      {form.clear_headers
                        ? t('deploy.httpHeadersRemoved')
                        : t('deploy.httpHeadersStored', { names: editing.http_header_names.join(', ') })}
                      {' '}
                      <button type="button" className="text-link" onClick={form.clear_headers ? clearHeaders : removeStoredHeaders}>
                        {form.clear_headers ? t('deploy.httpHeadersKeep') : t('common.remove')}
                      </button>
                    </>
                  ) : undefined} />
                <Textarea id="deploy-body" mono rows={6} spellCheck={false} required label={t('deploy.bodyTemplate')}
                  placeholder={HTTP_TEMPLATE_EXAMPLE} value={form.body_template} onChange={field('body_template')}
                  hint={<>{t('deploy.bodyTemplateHint', TEMPLATE_HINT_VARS)}{' '}<span className="mono">{HTTP_TEMPLATE_VARIABLES.map(v => `{{${v}}}`).join(' ')}</span></>} />
                <ToggleSwitch checked={form.allow_private_key} onChange={(v) => setForm({ ...form, allow_private_key: v })}
                  label={t('deploy.allowPrivateKey')} description={t('deploy.allowPrivateKeyHint', { keyVariable: '{{key_pem}}' })} />
                <Textarea id="deploy-tls-ca" mono rows={3} spellCheck={false} label={t('deploy.tlsCaPem')} placeholder="-----BEGIN CERTIFICATE-----"
                  value={form.tls_ca_pem} onChange={field('tls_ca_pem')} hint={t('deploy.tlsCaPemHint')} />
              </>
            )}
            {!isHttp && (
              <>
                <Input id="deploy-host" mono label={t('deploy.host')} value={form.host} onChange={field('host')} required maxLength={255}
                  hint={<><button type="button" className="text-link" onClick={applySameHostPreset}>{t('deploy.sameHost')}</button>{' '}{t('deploy.sameHostHint')}</>} />
                <NumberInput id="deploy-port" label={t('deploy.port')} value={form.port} onChange={field('port')} />
                <Textarea id="deploy-key" mono rows={4} spellCheck={false}
                  label={editing ? t('deploy.privateKeyRotate') : t(fips ? 'deploy.privateKeyOptionalFips' : 'deploy.privateKeyOptional')}
                  placeholder={t('deploy.privateKeyPlaceholder')} value={form.private_key} onChange={field('private_key')} />
              </>
            )}
            {editing && (
              <ToggleSwitch checked={form.enabled} onChange={(v) => setForm({ ...form, enabled: v })} label={t('common.enabled')} />
            )}
          </div>
          <div className="modal-actions">
            {!isHttp && editing?.host_key_pinned && (
              <Btn tone="danger" onClick={handleResetHostKey} disabled={saving || undefined}>{t('deploy.resetHostKey')}</Btn>
            )}
            <button type="button" className="btn" data-action="close-modal" disabled={saving || undefined} onClick={() => setFormOpen(false)}>{t('common.cancel')}</button>
            <Btn type="submit" tone="primary" icon="check" disabled={saving || undefined}>{editing ? t('common.save') : t('common.create')}</Btn>
          </div>
        </form>
      </Modal>

      {/* Public key: install it in the target's authorized_keys */}
      <Modal open={!!publicKeyFor} onClose={() => setPublicKeyFor(null)} title={t('deploy.publicKeyTitle')}>
        <div className="settings-stack">
          <p className="small muted">{t('deploy.publicKeyHint', { username: publicKeyFor?.username || '' })}</p>
          <pre className="public-key mono">{publicKeyFor?.public_key || t('deploy.publicKeyUnavailable')}</pre>
        </div>
        <div className="modal-actions">
          <Btn icon={isCopied() ? 'check' : 'copy'} onClick={copyPublicKey} disabled={!publicKeyFor?.public_key || undefined}>{t('common.copy')}</Btn>
          <button type="button" className="btn primary" data-write="false" data-action="close-modal" onClick={() => setPublicKeyFor(null)}>{t('common.close')}</button>
        </div>
      </Modal>
    </>
  )
}
