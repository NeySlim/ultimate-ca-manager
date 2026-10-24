import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash, Copy, Warning, ShieldCheck, LockKey } from '@phosphor-icons/react'
import { Button, Badge, Input, Select, Modal, Textarea, Tabs } from '../../components'
import { acmeService } from '../../services'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks'
import { formatDate } from '../../lib/utils'
import { DNS_UPDATE_ALGORITHMS, buildDnsUpdateSnippets, hostFromBase } from './dnsUpdateSnippets'

const EMPTY_FORM = { name: '', algorithm: 'hmac-sha256', eabCredentialId: '', notes: '' }

const SNIPPET_TABS = [
  ['bind', 'tabBind'],
  ['acmesh', 'tabAcmesh'],
  ['certbot', 'tabCertbot'],
  ['lego', 'tabLego'],
  ['certmanager', 'tabCertManager'],
  ['winacme', 'tabWinAcme'],
  ['poshacme', 'tabPoshAcme'],
]

function CopyField({ label, value, onCopy, testId }) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">{label}</label>
      <div className="flex items-center gap-2">
        <code data-testid={testId} className="flex-1 px-3 py-2 rounded bg-bg-tertiary font-mono text-sm break-all">{value}</code>
        <Button type="button" variant="secondary" size="sm" onClick={() => onCopy(value)} title={label}>
          <Copy size={14} />
        </Button>
      </div>
    </div>
  )
}

/**
 * DNS UPDATE (RFC 2136) TSIG keys of one ACME proxy account: list, create
 * (the secret is shown once), revoke and delete.
 */
export default function DnsUpdateKeysPanel({
  account,
  proxyPublicBase = '',
  dnsUpdatePort = 0,
  canWrite,
  canDelete,
}) {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { copy } = useClipboard()

  const [keys, setKeys] = useState([])
  const [eabCredentials, setEabCredentials] = useState([])
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [created, setCreated] = useState(null)
  const [busy, setBusy] = useState(false)

  const accountId = account.id

  const loadKeys = useCallback(async () => {
    try {
      const res = await acmeService.listDnsUpdateKeys(accountId)
      setKeys(res?.data || [])
    } catch (error) {
      showError(error.message || t('acme.dnsUpdate.loadFailed'))
    }
  }, [accountId, showError, t])

  useEffect(() => { loadKeys() }, [loadKeys])

  useEffect(() => {
    acmeService.listEabCredentials()
      .then((res) => setEabCredentials((res?.data || []).filter((c) => c.status !== 'revoked')))
      .catch(() => {})
  }, [])

  const eabLabel = (cred) => cred.label || cred.kid
  const eabById = (id) => eabCredentials.find((c) => c.id === id)

  const closeCreate = () => { setShowCreate(false); setForm(EMPTY_FORM) }

  const handleCreate = async () => {
    setBusy(true)
    try {
      const body = { algorithm: form.algorithm }
      if (form.name.trim()) body.name = form.name.trim()
      if (form.eabCredentialId) body.eab_credential_id = parseInt(form.eabCredentialId, 10)
      if (form.notes.trim()) body.notes = form.notes.trim()
      const res = await acmeService.createDnsUpdateKey(accountId, body)
      setCreated(res?.data || res)
      closeCreate()
      await loadKeys()
    } catch (error) {
      showError(error.message || t('acme.dnsUpdate.createFailed'))
    } finally {
      setBusy(false)
    }
  }

  const handleRevoke = async (key) => {
    const confirmed = await showConfirm(
      t('acme.dnsUpdate.confirmRevoke', { name: key.name }),
      { title: t('acme.dnsUpdate.revokeTitle'), confirmText: t('acme.dnsUpdate.revoke'), variant: 'danger' },
    )
    if (!confirmed) return
    try {
      await acmeService.deleteDnsUpdateKey(accountId, key.id)
      showSuccess(t('acme.dnsUpdate.revokedSuccess'))
      await loadKeys()
    } catch (error) {
      showError(error.message || t('acme.dnsUpdate.revokeFailed'))
    }
  }

  const handleDelete = async (key) => {
    const confirmed = await showConfirm(
      t('acme.dnsUpdate.confirmDelete', { name: key.name }),
      { title: t('acme.dnsUpdate.deleteTitle'), confirmText: t('acme.dnsUpdate.delete'), variant: 'danger' },
    )
    if (!confirmed) return
    try {
      await acmeService.deleteDnsUpdateKey(accountId, key.id)
      showSuccess(t('acme.dnsUpdate.deletedSuccess'))
      await loadKeys()
    } catch (error) {
      showError(error.message || t('acme.dnsUpdate.deleteFailed'))
    }
  }

  const copyValue = (value, messageKey) => {
    copy(value)
    showSuccess(t(messageKey))
  }

  const base = (proxyPublicBase || '').replace(/\/$/, '')
  const directoryUrl = `${base || `${window.location.origin}/acme/proxy`}/${account.proxy_slug || '<slug>'}/directory`
  const portConfigured = Number(dnsUpdatePort) > 0
  const port = portConfigured ? Number(dnsUpdatePort) : 53

  const renderSnippets = () => {
    const snippets = buildDnsUpdateSnippets({
      keyName: created.name,
      algorithm: created.algorithm,
      secret: created.secret,
      host: hostFromBase(base || window.location.origin),
      port,
      directoryUrl,
    })
    return (
      <div className="space-y-2">
        <p className="text-sm font-medium">{t('acme.dnsUpdate.snippets')}</p>
        <p className="text-xs text-text-tertiary">{t('acme.dnsUpdate.snippetsHelp')}</p>
        <p className="text-xs text-text-tertiary">
          {portConfigured
            ? t('acme.dnsUpdate.notePort', { port })
            : t('acme.dnsUpdate.notePortDisabled')}
        </p>
        <Tabs
          tabs={SNIPPET_TABS.map(([id, labelKey]) => {
            const snippet = snippets.find((s) => s.id === id)
            return {
              id,
              label: t(`acme.dnsUpdate.${labelKey}`),
              content: (
                <div className="space-y-2">
                  {snippet.noteKeys.map((noteKey) => (
                    <p
                      key={noteKey}
                      data-testid={`dns-update-note-${noteKey}`}
                      className={snippet.unsupported && noteKey === 'noteCertManagerSha384'
                        ? 'text-sm status-warning-text'
                        : 'text-xs text-text-tertiary'}
                    >
                      {t(`acme.dnsUpdate.${noteKey}`)}
                    </p>
                  ))}
                  {snippet.code && (
                    <div className="relative">
                      <pre
                        data-testid={`dns-update-snippet-${id}`}
                        className="p-3 pr-12 rounded bg-bg-tertiary font-mono text-xs overflow-x-auto whitespace-pre"
                      >{snippet.code}</pre>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        className="absolute top-2 right-2"
                        onClick={() => copyValue(snippet.code, 'acme.dnsUpdate.codeCopied')}
                        title={t('common.copy')}
                      >
                        <Copy size={14} />
                      </Button>
                    </div>
                  )}
                </div>
              ),
            }
          })}
        />
      </div>
    )
  }

  return (
    <div className="mt-2 p-3 bg-bg-secondary rounded-lg border border-border space-y-3" data-testid="dns-update-keys-panel">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-text-primary flex items-center gap-2">
          <ShieldCheck size={16} /> {t('acme.dnsUpdate.title')}
        </p>
        {canWrite && (
          <Button type="button" size="sm" onClick={() => setShowCreate(true)}>
            <Plus size={12} /> {t('acme.dnsUpdate.create')}
          </Button>
        )}
      </div>
      <p className="text-xs text-text-tertiary">{t('acme.dnsUpdate.intro')}</p>

      {keys.length === 0 ? (
        <p className="text-xs text-text-tertiary py-2 text-center">{t('acme.dnsUpdate.empty')}</p>
      ) : (
        <div className="divide-y divide-border">
          {keys.map((key) => {
            const cred = key.eab_credential_id ? eabById(key.eab_credential_id) : null
            return (
              <div key={key.id} className="py-2 flex items-start justify-between gap-2" data-testid={`dns-update-key-${key.id}`}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-mono break-all">{key.name}</span>
                    <Badge variant="secondary" size="sm">{key.algorithm}</Badge>
                    <Badge variant={key.status === 'active' ? 'success' : 'danger'} size="sm">
                      {key.status === 'active' ? t('acme.dnsUpdate.statusActive') : t('acme.dnsUpdate.statusRevoked')}
                    </Badge>
                    {key.eab_bound && !key.eab_credential_id && (
                      <Badge variant="warning" size="sm" title={t('acme.dnsUpdate.eabMissingHelp')} data-testid={`dns-update-eab-missing-${key.id}`}>
                        <Warning size={10} /> {t('acme.dnsUpdate.eabMissing')}
                      </Badge>
                    )}
                    {key.eab_credential_id && (
                      <Badge variant="outline" size="sm">
                        <LockKey size={10} /> {cred ? eabLabel(cred) : `EAB #${key.eab_credential_id}`}
                      </Badge>
                    )}
                  </div>
                  <div className="mt-1 text-xs text-text-tertiary">
                    {t('acme.dnsUpdate.created')}: {formatDate(key.created_at)}
                    {' · '}{t('acme.dnsUpdate.lastUsed')}: {key.last_used_at ? formatDate(key.last_used_at) : t('acme.dnsUpdate.never')}
                  </div>
                  {key.notes && <div className="mt-1 text-xs text-text-tertiary">{key.notes}</div>}
                </div>
                <div className="flex gap-1 shrink-0">
                  {canDelete && key.status === 'active' && (
                    <Button type="button" variant="ghost" size="sm" onClick={() => handleRevoke(key)} title={t('acme.dnsUpdate.revoke')}>
                      <Trash size={14} className="text-yellow-500" />
                    </Button>
                  )}
                  {canDelete && key.status === 'revoked' && (
                    <Button type="button" variant="ghost" size="sm" onClick={() => handleDelete(key)} title={t('acme.dnsUpdate.delete')}>
                      <Trash size={14} className="text-red-500" />
                    </Button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Create dialog */}
      <Modal open={showCreate} onClose={closeCreate} title={t('acme.dnsUpdate.newTitle')}>
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-tertiary">{t('acme.dnsUpdate.newDescription')}</p>
          <Input
            label={t('acme.dnsUpdate.name')}
            aria-label={t('acme.dnsUpdate.name')}
            value={form.name}
            onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
            placeholder={t('acme.dnsUpdate.namePlaceholder')}
            helperText={t('acme.dnsUpdate.nameHelp')}
            maxLength={253}
          />
          <Select
            label={t('acme.dnsUpdate.algorithm')}
            value={form.algorithm}
            onChange={(val) => setForm((p) => ({ ...p, algorithm: val }))}
            options={DNS_UPDATE_ALGORITHMS.map((a) => ({ value: a, label: a }))}
            helperText={t('acme.dnsUpdate.algorithmHelp')}
          />
          <Select
            label={t('acme.dnsUpdate.eabCredential')}
            value={form.eabCredentialId}
            onChange={(val) => setForm((p) => ({ ...p, eabCredentialId: val }))}
            options={[
              { value: '', label: t('acme.dnsUpdate.eabNone') },
              ...eabCredentials.map((c) => ({ value: String(c.id), label: eabLabel(c) })),
            ]}
            helperText={t('acme.dnsUpdate.eabHelp')}
          />
          <Textarea
            label={t('acme.dnsUpdate.notes')}
            aria-label={t('acme.dnsUpdate.notes')}
            value={form.notes}
            onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))}
            placeholder={t('acme.dnsUpdate.notesPlaceholder')}
            rows={2}
            maxLength={1000}
          />
          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button type="button" variant="secondary" onClick={closeCreate}>{t('common.cancel')}</Button>
            <Button type="button" onClick={handleCreate} disabled={busy}>{t('acme.dnsUpdate.generate')}</Button>
          </div>
        </div>
      </Modal>

      {/* Secret shown once */}
      <Modal
        open={!!created}
        onClose={() => setCreated(null)}
        title={t('acme.dnsUpdate.secretTitle')}
        size="lg"
      >
        {created && (
          <div className="p-4 space-y-4">
            <div className="rounded-lg border border-yellow-500/40 bg-yellow-500/10 p-3 flex gap-2">
              <Warning size={20} className="text-yellow-500 shrink-0 mt-0.5" weight="duotone" />
              <div className="text-sm">
                <div className="font-semibold">{t('acme.dnsUpdate.secretWarningTitle')}</div>
                <div className="text-text-tertiary mt-1">{t('acme.dnsUpdate.secretWarning')}</div>
              </div>
            </div>
            <CopyField
              label={t('acme.dnsUpdate.keyName')}
              value={created.name}
              testId="dns-update-created-name"
              onCopy={(v) => copyValue(v, 'acme.dnsUpdate.nameCopied')}
            />
            <CopyField
              label={t('acme.dnsUpdate.algorithm')}
              value={created.algorithm}
              testId="dns-update-created-algorithm"
              onCopy={(v) => copyValue(v, 'acme.dnsUpdate.algorithmCopied')}
            />
            <CopyField
              label={t('acme.dnsUpdate.secret')}
              value={created.secret}
              testId="dns-update-created-secret"
              onCopy={(v) => copyValue(v, 'acme.dnsUpdate.secretCopied')}
            />
            {renderSnippets()}
            <div className="flex justify-end pt-2 border-t border-border">
              <Button type="button" onClick={() => setCreated(null)}>{t('acme.dnsUpdate.secretConfirm')}</Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
