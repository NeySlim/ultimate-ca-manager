import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Copy, Warning } from '@phosphor-icons/react'
import { Btn, Icon, Pill, RecordList } from '../../components/atelier'
import { Button, Input, Select, Modal, Textarea, Tabs } from '../../components'
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
 * (the secret is shown once), revoke and delete. ``proxyActive`` is true when
 * the proxy of the account is enabled with a slug. When it is off, the keys do
 * not work: a key cannot be created, but it can still be revoked or deleted.
 */
export default function DnsUpdateKeysPanel({
  account,
  proxyPublicBase = '',
  dnsUpdatePort = 0,
  proxyActive = true,
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

  // The keys of the account as the mockup's record rows, in a section of the upstream account dock
  const keyBadge = (key) => <Pill label={key.status === 'active' ? t('acme.dnsUpdate.statusActive') : t('acme.dnsUpdate.statusRevoked')} tone={key.status === 'active' ? 'good' : 'bad'} />
  return (
    <section data-testid="dns-update-keys-panel">
      <h3 className="section-title">{t('acme.dnsUpdate.title')}</h3>
      <p className="muted small">{t('acme.dnsUpdate.intro')}</p>
      {!proxyActive && (
        <p className="notice warn" data-testid="dns-update-proxy-off"><Icon name="warning" /><span>{t('acme.dnsUpdate.proxyOff')}</span></p>
      )}
      <RecordList empty={t('acme.dnsUpdate.empty')}>
        {keys.map((key) => {
          const cred = key.eab_credential_id ? eabById(key.eab_credential_id) : null
          return (
            <li key={key.id} data-testid={`dns-update-key-${key.id}`}>
              <div className="rl-main">
                <strong className="mono">{key.name}</strong>
                <span className="rl-meta">
                  <span>{key.algorithm}</span>
                  {key.eab_credential_id ? <>{' · EAB '}<span>{cred ? eabLabel(cred) : `#${key.eab_credential_id}`}</span></> : ''}
                  {' · '}{t('acme.dnsUpdate.created')} {formatDate(key.created_at)}
                  {' · '}{t('acme.dnsUpdate.lastUsed')} {key.last_used_at ? formatDate(key.last_used_at) : t('acme.dnsUpdate.never')}
                </span>
                {key.notes && <span className="rl-meta">{key.notes}</span>}
                {key.eab_bound && !key.eab_credential_id && (
                  <p className="rl-error" title={t('acme.dnsUpdate.eabMissingHelp')} data-testid={`dns-update-eab-missing-${key.id}`}>
                    <Icon name="warning" /><span>{t('acme.dnsUpdate.eabMissing')}</span>
                  </p>
                )}
              </div>
              {keyBadge(key)}
              {canDelete && (
                <div className="rl-action">
                  {key.status === 'active' && <Btn icon="block" onClick={() => handleRevoke(key)} title={t('acme.dnsUpdate.revoke')}>{t('acme.dnsUpdate.revoke')}</Btn>}
                  {key.status === 'revoked' && <Btn icon="close" onClick={() => handleDelete(key)} title={t('acme.dnsUpdate.delete')}>{t('acme.dnsUpdate.delete')}</Btn>}
                </div>
              )}
            </li>
          )
        })}
      </RecordList>
      {canWrite && (
        <div className="copy-url">
          <Btn icon="plus" write disabled={!proxyActive || undefined} onClick={() => setShowCreate(true)}>{t('acme.dnsUpdate.create')}</Btn>
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
            <div className="rounded-lg border border-status-warning-op40 bg-status-warning-op10 p-3 flex gap-2">
              <Warning size={20} className="text-status-warning shrink-0 mt-0.5" weight="duotone" />
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
    </section>
  )
}
