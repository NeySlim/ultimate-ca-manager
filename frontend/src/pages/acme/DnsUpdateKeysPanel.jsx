import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Icon, IconBtn, Pill, RecordList } from '../../components/atelier'
import { Input, Select, Textarea, Modal } from '../../components/atelier/Form'
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

// A value to copy, as the mockup's command line: the value on one line that scrolls, then its copy button
function CopyField({ label, value, onCopy, testId }) {
  return (
    <div className="field full">
      <span>{label}</span>
      <div className="command-line" style={{ margin: 0 }}>
        <code data-testid={testId} className="mono">{value}</code>
        <IconBtn icon="copy" label={label} onClick={() => onCopy(value)} />
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
  const [snippetTab, setSnippetTab] = useState(null)

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
    const snippet = snippets.find((s) => s.id === snippetTab) || snippets.find((s) => s.id === SNIPPET_TABS[0][0])
    return (
      <fieldset className="field full" aria-describedby="hint-dns-update-snippets">
        <legend>{t('acme.dnsUpdate.snippets')}</legend>
        <small id="hint-dns-update-snippets">
          <span>{t('acme.dnsUpdate.snippetsHelp')}</span>{' '}
          <span>{portConfigured ? t('acme.dnsUpdate.notePort', { port }) : t('acme.dnsUpdate.notePortDisabled')}</span>
        </small>
        <div className="segmented" role="group" aria-label={t('acme.dnsUpdate.snippets')}>
          {SNIPPET_TABS.map(([id, labelKey]) => (
            <button key={id} type="button" aria-pressed={snippet.id === id} onClick={() => setSnippetTab(id)}>{t(`acme.dnsUpdate.${labelKey}`)}</button>
          ))}
        </div>
        {snippet.noteKeys.map((noteKey) => (
          snippet.unsupported && noteKey === 'noteCertManagerSha384'
            ? <p key={noteKey} className="notice warn" data-testid={`dns-update-note-${noteKey}`} style={{ margin: 0 }}><Icon name="warning" /><span>{t(`acme.dnsUpdate.${noteKey}`)}</span></p>
            : <small key={noteKey} data-testid={`dns-update-note-${noteKey}`}>{t(`acme.dnsUpdate.${noteKey}`)}</small>
        ))}
        {snippet.code && (
          <>
            <pre data-testid={`dns-update-snippet-${snippet.id}`} className="code-preview" style={{ margin: 0, whiteSpace: 'pre', overflowX: 'auto' }}>{snippet.code}</pre>
            <div className="actions">
              <Btn icon="copy" onClick={() => copyValue(snippet.code, 'acme.dnsUpdate.codeCopied')}>{t('common.copy')}</Btn>
            </div>
          </>
        )}
      </fieldset>
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
      <Modal open={showCreate} onClose={closeCreate} title={t('acme.dnsUpdate.newTitle')} subtitle={t('acme.dnsUpdate.newDescription')} testId="dns-update-create-dialog">
        <form noValidate onSubmit={(e) => { e.preventDefault(); handleCreate() }}>
          <div className="form-fields">
            <Input id="dns-update-name" label={t('acme.dnsUpdate.name')} full value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              placeholder={t('acme.dnsUpdate.namePlaceholder')} helperText={t('acme.dnsUpdate.nameHelp')} maxLength={253} data-autofocus="" />
            <Select id="dns-update-algorithm" label={t('acme.dnsUpdate.algorithm')} value={form.algorithm} onChange={(val) => setForm((p) => ({ ...p, algorithm: val }))}
              options={DNS_UPDATE_ALGORITHMS.map((a) => ({ value: a, label: a }))} helperText={t('acme.dnsUpdate.algorithmHelp')} />
            <Select id="dns-update-eab" label={t('acme.dnsUpdate.eabCredential')} value={form.eabCredentialId} onChange={(val) => setForm((p) => ({ ...p, eabCredentialId: val }))}
              options={[
                { value: '', label: t('acme.dnsUpdate.eabNone') },
                ...eabCredentials.map((c) => ({ value: String(c.id), label: eabLabel(c) })),
              ]}
              helperText={t('acme.dnsUpdate.eabHelp')} />
            <Textarea id="dns-update-notes" label={t('acme.dnsUpdate.notes')} value={form.notes} onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))}
              placeholder={t('acme.dnsUpdate.notesPlaceholder')} rows={2} maxLength={1000} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" data-action="close-modal" onClick={closeCreate}>{t('common.cancel')}</button>
            <button type="submit" className="btn primary" disabled={busy || undefined}>{t('acme.dnsUpdate.generate')}</button>
          </div>
        </form>
      </Modal>

      {/* Secret shown once */}
      <Modal open={!!created} onClose={() => setCreated(null)} title={t('acme.dnsUpdate.secretTitle')} size="lg" testId="dns-update-secret-dialog">
        {created && (
          <>
            <div className="notice warn"><Icon name="warning" /><span><strong>{t('acme.dnsUpdate.secretWarningTitle')}</strong> {t('acme.dnsUpdate.secretWarning')}</span></div>
            <div className="form-fields">
              <CopyField label={t('acme.dnsUpdate.keyName')} value={created.name} testId="dns-update-created-name"
                onCopy={(v) => copyValue(v, 'acme.dnsUpdate.nameCopied')} />
              <CopyField label={t('acme.dnsUpdate.algorithm')} value={created.algorithm} testId="dns-update-created-algorithm"
                onCopy={(v) => copyValue(v, 'acme.dnsUpdate.algorithmCopied')} />
              <CopyField label={t('acme.dnsUpdate.secret')} value={created.secret} testId="dns-update-created-secret"
                onCopy={(v) => copyValue(v, 'acme.dnsUpdate.secretCopied')} />
              {renderSnippets()}
            </div>
            <div className="modal-actions">
              <button type="button" className="btn primary" data-write="false" onClick={() => setCreated(null)}>{t('acme.dnsUpdate.secretConfirm')}</button>
            </div>
          </>
        )}
      </Modal>
    </section>
  )
}
