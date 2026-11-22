import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Input, Modal, Textarea, ToggleSwitch } from '../../components/atelier/Form'
import { Btn, Icon, IconBtn, Pill, ListView, Dock, DockBody, Section, Props, EmptyBlock, NoMatch, Toolbar, SearchField, useClientList, useSortParam } from '../../components/atelier'
import { useDockId } from '../../components/atelier/useDockParam'
import { SlotDock } from '../protocols/dockSlot'
import { Copyable, Notice } from '../protocols/atelierParts'
import { fetchListing } from '../../lib/fetchAllPages'
import { dateOf, dateTimeOf } from '../admin/adminDates'
import { acmeService } from '../../services'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks'

// Every page is read (200 a page), so the list sorts and searches them all; the newest first (T4)
const EAB_MAX = 5000
// Every page of the server, so the search, the chips and the sort read the whole set
const readCredentials = () => fetchListing((page) => acmeService.listEabCredentials(undefined, page), { perPage: 200, max: EAB_MAX })
const NEWEST = { key: 'created', asc: false }
const SORT_KEYS = ['name', 'kid', 'domains', 'created', 'state']

// null (legacy, unrestricted) and any list holding '*' both mean all domains.
const isUnrestricted = (domains) => domains == null || domains.includes('*')

// Patterns are typed one per line or comma separated.
const parsePatterns = (text) => text.split(/[\n,]/).map(p => p.trim()).filter(Boolean)

// The form always sends an explicit list, never null.
const buildAllowedDomains = (allDomains, text) => (allDomains ? ['*'] : parsePatterns(text))

function AllowedDomainsField({ id, allDomains, onAllDomainsChange, text, onTextChange }) {
  const { t } = useTranslation()
  return (
    <>
      <ToggleSwitch id={`${id}-all`} label={t('acme.eab.allDomainsLabel')} checked={allDomains} onChange={onAllDomainsChange} />
      <Textarea id={`${id}-domains`} label={t('acme.eab.allowedDomains')} mono value={text} onChange={(e) => onTextChange(e.target.value)} disabled={allDomains}
        rows={4} placeholder={'example.com\n*.example.com'} helperText={t('acme.eab.allowedDomainsHelp')} />
    </>
  )
}

export default function EabTab({ eabRequired, onToggleEabRequired, showCreateModal, onCloseCreateModal, canWrite, canDelete }) {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const [loading, setLoading] = useState(true)
  // The open object lives in the URL (`item`)
  const { openId, setOpenId } = useDockId()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { copy } = useClipboard()

  const [eabCredentials, setEabCredentials] = useState([])
  const [partial, setPartial] = useState(null)
  const [eabFilterStatus, setEabFilterStatus] = useState('')
  const [eabQuery, setEabQuery] = useState('')
  const [showLocalCreate, setShowLocalCreate] = useState(false)
  const [newEabSecret, setNewEabSecret] = useState(null)
  const [eabLabel, setEabLabel] = useState('')
  const [eabExpiresInDays, setEabExpiresInDays] = useState('')
  const [eabAllDomains, setEabAllDomains] = useState(true)
  const [eabDomainsText, setEabDomainsText] = useState('')

  // Allowed-domains editing state
  const [editingDomainsCred, setEditingDomainsCred] = useState(null)
  const [editAllDomains, setEditAllDomains] = useState(true)
  const [editDomainsText, setEditDomainsText] = useState('')

  // Notes editing state
  const [editingNotesId, setEditingNotesId] = useState(null)
  const [editingNotesValue, setEditingNotesValue] = useState('')

  const reload = async () => {
    const { rows, partial: cut } = await readCredentials()
    setEabCredentials(rows)
    setPartial(cut)
  }

  useEffect(() => {
    readCredentials().then(({ rows, partial: cut }) => { setEabCredentials(rows); setPartial(cut) })
      .catch(() => {}).finally(() => setLoading(false))
  }, [])

  // The search reads the label, the key id, the domains, the notes and the bound account
  const searchedEabCredentials = useMemo(() => {
    const q = eabQuery.trim().toLowerCase()
    if (!q) return eabCredentials
    return eabCredentials.filter((c) => [c.label, c.kid, (c.allowed_domains || []).join(' '), c.notes, c.used_by_account_id]
      .some((v) => String(v || '').toLowerCase().includes(q)))
  }, [eabCredentials, eabQuery])
  const filteredEabCredentials = useMemo(() => {
    if (!eabFilterStatus) return searchedEabCredentials
    return searchedEabCredentials.filter(c => c.status === eabFilterStatus)
  }, [searchedEabCredentials, eabFilterStatus])

  const handleCreateEabCredential = async () => {
    try {
      const payload = { label: eabLabel || null }
      const days = parseInt(eabExpiresInDays, 10)
      if (!Number.isNaN(days) && days > 0) payload.expires_in_days = days

      payload.allowed_domains = buildAllowedDomains(eabAllDomains, eabDomainsText)
      const res = await acmeService.createEabCredential(payload)
      const created = res.data || res
      setNewEabSecret(created)
      setShowLocalCreate(false)
      onCloseCreateModal()
      setEabLabel('')
      setEabExpiresInDays('')
      setEabAllDomains(true)
      setEabDomainsText('')
      await reload()
    } catch (error) {
      showError(error.message || t('acme.eab.createFailed'))
    }
  }

  const handleRevokeEabCredential = async (cred) => {
    const confirmed = await showConfirm(
      t('acme.eab.confirmRevoke', { kid: cred.kid }),
      {
        title: t('acme.eab.revokeTitle'),
        confirmText: t('acme.eab.revoke'),
        variant: 'danger'
      }
    )
    if (!confirmed) return
    try {
      await acmeService.revokeEabCredential(cred.id)
      showSuccess(t('acme.eab.revokedSuccess'))
      await reload()
    } catch (error) {
      showError(error.message || t('acme.eab.revokeFailed'))
    }
  }

  // Permanent delete for used/revoked credentials
  const handleDeleteEabCredential = async (cred) => {
    const confirmed = await showConfirm(
      t('acme.eab.confirmDelete', { kid: cred.kid }),
      {
        title: t('acme.eab.deleteTitle'),
        confirmText: t('acme.eab.delete'),
        variant: 'danger'
      }
    )
    if (!confirmed) return
    try {
      await acmeService.deleteEabCredential(cred.id)
      showSuccess(t('acme.eab.deletedSuccess'))
      await reload()
    } catch (error) {
      showError(error.message || t('acme.eab.deleteFailed'))
    }
  }

  // Notes editing
  const startEditingNotes = (cred) => {
    setEditingNotesId(cred.id)
    setEditingNotesValue(cred.notes || '')
  }

  const cancelEditingNotes = () => {
    setEditingNotesId(null)
    setEditingNotesValue('')
  }

  const saveNotes = async (credId) => {
    try {
      await acmeService.patchEabCredential(credId, { notes: editingNotesValue || null })
      showSuccess(t('acme.eab.notesSaved'))
      await reload()
      setEditingNotesId(null)
      setEditingNotesValue('')
    } catch (error) {
      showError(error.message || t('acme.eab.notesSaveFailed'))
    }
  }

  // Allowed domains editing: the form opens on the stored state
  const startEditingDomains = (cred) => {
    const domains = cred.allowed_domains
    setEditingDomainsCred(cred)
    setEditAllDomains(isUnrestricted(domains))
    setEditDomainsText((domains || []).filter(p => p !== '*').join('\n'))
  }

  const closeEditingDomains = () => {
    setEditingDomainsCred(null)
    setEditAllDomains(true)
    setEditDomainsText('')
  }

  const saveDomains = async () => {
    if (!editingDomainsCred) return
    try {
      await acmeService.patchEabCredential(editingDomainsCred.id, {
        allowed_domains: buildAllowedDomains(editAllDomains, editDomainsText),
      })
      showSuccess(t('acme.eab.domainsSaved'))
      closeEditingDomains()
      await reload()
    } catch (error) {
      showError(error.message || t('acme.eab.domainsSaveFailed'))
    }
  }

  const isCreateOpen = showCreateModal || showLocalCreate
  const STATUS_TONES = { active: 'good', used: 'muted', revoked: 'bad' }
  const statusLabel = (c) => t(`acme.eab.status${c.status.charAt(0).toUpperCase() + c.status.slice(1)}`)
  const pill = (c) => <Pill label={statusLabel(c)} tone={STATUS_TONES[c.status] || 'muted'} />
  const domainsText = (c) => (isUnrestricted(c.allowed_domains) ? t('acme.eab.allDomains')
    : c.allowed_domains.length === 0 ? t('acme.eab.noDomains') : c.allowed_domains.join(', '))
  const open = eabCredentials.find((c) => c.id === openId)
  const name = (c) => c.label || t('acme.eab.unlabeled')
  const removeAction = (c) => (c.status === 'active'
    ? { icon: 'block', label: t('acme.eab.revoke'), onClick: () => handleRevokeEabCredential(c) }
    : { icon: 'close', label: t('acme.eab.delete'), onClick: () => handleDeleteEabCredential(c) })

  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: 'EAB' })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: name(open), icon: 'lock' }]} onClose={() => setOpenId(null)}>
      <DockBody icon="lock" title={name(open)} badge={pill(open)} section="cred" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name: name(open) })} sections={[['cred', t('atelier.overview')]]}
        actions={<>
          {canWrite && <Btn icon="settings" write id="eab-edit-domains" onClick={() => startEditingDomains(open)}>{t('acme.eab.editDomainsTitle')}</Btn>}
          {canWrite && <Btn icon="file" write id="eab-edit-notes" onClick={() => startEditingNotes(open)}>{t('acme.eab.editNotesTitle')}</Btn>}
          {canDelete && open.status === 'active' && <Btn tone="danger" icon="block" onClick={() => handleRevokeEabCredential(open)}>{t('acme.eab.revoke')}</Btn>}
          {canDelete && open.status !== 'active' && <Btn icon="close" onClick={() => handleDeleteEabCredential(open)}>{t('acme.eab.delete')}</Btn>}
        </>}>
        <div className="module-detail">
          <Section title={t('atelier.properties')}>
            <Props items={[
              [t('acme.eab.kid'), <Copyable key="k" value={open.kid} label={t('acme.eab.kid')} />],
              [t('atelier.state'), pill(open)],
              [t('acme.eab.allowedDomains'), <span key="d" className="mono" data-testid={`eab-dock-domains-${open.id}`}>{domainsText(open)}</span>],
              [t('acme.eab.created'), dateTimeOf(open.created_at, locale)],
              open.expires_at && [t('common.expires'), dateTimeOf(open.expires_at, locale)],
              open.used_at && [t('acme.eab.usedAt'), dateTimeOf(open.used_at, locale)],
              open.used_by_account_id && [t('acme.eab.boundTo'), <span key="b" className="mono">{open.used_by_account_id}</span>],
              open.revoked_at && [t('acme.eab.revokedAt'), dateTimeOf(open.revoked_at, locale)],
            ]} />
          </Section>
          <Section title={t('acme.eab.notes')}>
            <p className="summary">{open.notes || <span className="muted">{t('acme.eab.noNotes')}</span>}</p>
          </Section>
        </div>
      </DockBody>
    </Dock>
  )

  // Every page of the server is read (or the list says it is partial): sorted and paged here
  const sortParam = useSortParam(NEWEST, SORT_KEYS)
  const list = useClientList(filteredEabCredentials, {
    resetKey: `${eabQuery}|${eabFilterStatus}`,
    sortParam,
    sorts: {
      name: (c) => c.label, kid: (c) => c.kid, domains: (c) => (isUnrestricted(c.allowed_domains) ? '*' : (c.allowed_domains || []).join(', ')),
      created: (c) => c.created_at && Date.parse(c.created_at), state: (c) => ({ active: 0, used: 1, revoked: 2 })[c.status] ?? null,
    },
  })

  return (
    <>
      {partial && <Notice tone="warn" role="status">{t('acme.eab.listPartial', partial)}</Notice>}
      <ListView label="EAB" caption={t('acme.eab.caption')} icon="lock" list={list} nameSort="name" loading={loading}
        filters={{
          views: ['', 'active', 'used', 'revoked'].map((s) => ({
            id: s, label: s ? t(`acme.eab.status${s.charAt(0).toUpperCase() + s.slice(1)}`) : t('common.all'),
            count: s ? searchedEabCredentials.filter((c) => c.status === s).length : searchedEabCredentials.length,
          })),
          active: eabFilterStatus, onChange: setEabFilterStatus, label: t('acme.filterByState'),
          aside: (
            <label className="checkbox-line eab-required" title={t('acme.eab.requiredDescription')}>
              <input type="checkbox" checked={!!eabRequired} disabled={!canWrite || undefined} onChange={(e) => onToggleEabRequired(e.target.checked)} />
              {t('acme.eab.requiredTitle')}
            </label>
          ),
        }}
        toolbar={(
          <Toolbar>
            <SearchField id="acme-eab-search" name="q" label={t('acme.eab.search')} placeholder={t('acme.eab.search')} value={eabQuery} onChange={setEabQuery} />
          </Toolbar>
        )}
        title={name} status={pill} openedId={openId} onOpen={(c) => setOpenId(c.id)}
        columns={[
          { id: 'kid', label: t('acme.eab.kid'), cell: (c) => <span className="mono">{c.kid}</span>, kind: 'text', priority: 4, title: (c) => c.kid, sort: 'kid' },
          { id: 'domains', label: t('acme.eab.allowedDomains'), cell: (c) => <span data-testid={`eab-domains-${c.id}`}>{domainsText(c)}</span>, grow: true,
            kind: 'text', priority: 3, title: domainsText, sort: 'domains' },
          { id: 'created', label: t('acme.eab.created'), labelFull: t('table.fullCreated'), cell: (c) => dateOf(c.created_at, locale) || '—', kind: 'fit', priority: 2, labelled: true, sort: 'created' },
          { status: true, sort: 'state' },
        ]}
        rowActions={canDelete ? (c) => [removeAction(c)] : undefined}
        empty={eabCredentials.length ? (
          <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')} onReset={() => { setEabQuery(''); setEabFilterStatus('') }} />
        ) : (
          <EmptyBlock id="acme-eab" icon="lock" title={t('acme.eab.empty')} text={t('acme.eab.emptyDesc')}
            action={canWrite ? { label: t('acme.eab.new'), icon: 'plus', onClick: () => setShowLocalCreate(true), primary: true } : undefined} />
        )}
        footer={{ range: list.paged ? t('table.range', { start: list.start, end: list.end, total: list.total }) : t('acme.eab.totalCount', { count: list.total }) }} />
      <SlotDock>{dock}</SlotDock>

      {editingNotesId !== null && (
        <Modal open onClose={cancelEditingNotes} title={t('acme.eab.editNotesTitle')} size="sm" testId="eab-notes-dialog">
          <form noValidate onSubmit={(e) => { e.preventDefault(); saveNotes(editingNotesId) }}>
            <div className="form-fields">
              <Textarea id="eab-notes" label={t('acme.eab.notes')} placeholder={t('acme.eab.notesPlaceholder')} value={editingNotesValue}
                onChange={(e) => setEditingNotesValue(e.target.value)} rows={3} data-autofocus="" />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" data-action="close-modal" onClick={cancelEditingNotes}>{t('common.cancel')}</button>
              <button type="submit" className="btn primary">{t('common.save')}</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Create EAB Credential Modal */}
      <Modal open={isCreateOpen} onClose={() => { setShowLocalCreate(false); onCloseCreateModal() }} title={t('acme.eab.newTitle')}
        subtitle={t('acme.eab.newDescription')} testId="eab-create-dialog">
        <form noValidate onSubmit={(e) => { e.preventDefault(); handleCreateEabCredential() }}>
          <div className="form-fields">
            <Input id="eab-label" label={t('acme.eab.label')} placeholder={t('acme.eab.labelPlaceholder')} value={eabLabel}
              onChange={(e) => setEabLabel(e.target.value)} maxLength={255} data-autofocus="" />
            <Input id="eab-expires" label={t('acme.eab.expiresInDays')} type="number" placeholder={t('acme.eab.expiresPlaceholder')} value={eabExpiresInDays}
              onChange={(e) => setEabExpiresInDays(e.target.value)} min={1} helperText={t('acme.eab.expiresHelp')} />
            <AllowedDomainsField id="eab-create" allDomains={eabAllDomains} onAllDomainsChange={setEabAllDomains} text={eabDomainsText} onTextChange={setEabDomainsText} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" data-action="close-modal" onClick={() => { setShowLocalCreate(false); onCloseCreateModal() }}>{t('common.cancel')}</button>
            <button type="submit" className="btn primary">{t('acme.eab.generate')}</button>
          </div>
        </form>
      </Modal>

      {/* Show EAB Secret Once Modal */}
      <Modal open={!!newEabSecret} onClose={() => setNewEabSecret(null)} title={t('acme.eab.secretTitle')} testId="eab-secret-dialog">
        {newEabSecret && (
          <>
            <div className="notice warn"><Icon name="warning" /><span><strong>{t('acme.eab.secretWarningTitle')}</strong> {t('acme.eab.secretWarning')}</span></div>
            <div className="form-fields">
              <div className="field full">
                <span>{t('acme.eab.kid')}</span>
                <div className="command-line" style={{ margin: 0 }}>
                  <code className="mono">{newEabSecret.kid}</code>
                  <IconBtn icon="copy" label={t('acme.eab.kid')} onClick={() => { copy(newEabSecret.kid); showSuccess(t('acme.eab.kidCopied')) }} />
                </div>
              </div>
              <div className="field full">
                <span>{t('acme.eab.hmacKey')}</span>
                <div className="command-line" style={{ margin: 0 }}>
                  <code className="mono">{newEabSecret.hmac_key}</code>
                  <IconBtn icon="copy" label={t('acme.eab.hmacKey')} onClick={() => { copy(newEabSecret.hmac_key); showSuccess(t('acme.eab.hmacCopied')) }} />
                </div>
                <small>{t('acme.eab.hmacFormat')}</small>
              </div>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn primary" data-write="false" onClick={() => setNewEabSecret(null)}>{t('acme.eab.secretConfirm')}</button>
            </div>
          </>
        )}
      </Modal>

      {/* Edit allowed domains Modal */}
      <Modal open={!!editingDomainsCred} onClose={closeEditingDomains} title={t('acme.eab.editDomainsTitle')} size="sm" testId="eab-domains-dialog">
        <form noValidate onSubmit={(e) => { e.preventDefault(); saveDomains() }}>
          <div className="form-fields">
            <AllowedDomainsField id="eab-edit" allDomains={editAllDomains} onAllDomainsChange={setEditAllDomains} text={editDomainsText} onTextChange={setEditDomainsText} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" data-action="close-modal" onClick={closeEditingDomains}>{t('common.cancel')}</button>
            <button type="submit" className="btn primary">{t('common.save')}</button>
          </div>
        </form>
      </Modal>
    </>
  )
}
