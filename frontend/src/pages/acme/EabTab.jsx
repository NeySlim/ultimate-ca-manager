import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Copy, Warning } from '@phosphor-icons/react'
import { Button, Input, Modal, Textarea } from '../../components'
import { Btn, Pill, ListView, Dock, DockBody, Section, Props, EmptyBlock, NoMatch } from '../../components/atelier'
import { SlotDock } from '../protocols/dockSlot'
import { Copyable } from '../protocols/atelierParts'
import { dateOf, dateTimeOf } from '../admin/adminDates'
import { acmeService } from '../../services'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks'

// null (legacy, unrestricted) and any list holding '*' both mean all domains.
const isUnrestricted = (domains) => domains == null || domains.includes('*')

// Patterns are typed one per line or comma separated.
const parsePatterns = (text) => text.split(/[\n,]/).map(p => p.trim()).filter(Boolean)

// The form always sends an explicit list, never null.
const buildAllowedDomains = (allDomains, text) => (allDomains ? ['*'] : parsePatterns(text))

function AllowedDomainsField({ allDomains, onAllDomainsChange, text, onTextChange }) {
  const { t } = useTranslation()
  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={allDomains}
          onChange={(e) => onAllDomainsChange(e.target.checked)}
          className="rounded border-border bg-bg-tertiary"
        />
        <span className="text-sm text-text-primary">{t('acme.eab.allDomainsLabel')}</span>
      </label>
      <Textarea
        label={t('acme.eab.allowedDomains')}
        aria-label={t('acme.eab.allowedDomains')}
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
        disabled={allDomains}
        rows={4}
        placeholder={'example.com\n*.example.com'}
        helperText={t('acme.eab.allowedDomainsHelp')}
        className="font-mono"
      />
    </div>
  )
}

export default function EabTab({ eabRequired, onToggleEabRequired, showCreateModal, onCloseCreateModal, canWrite, canDelete }) {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const [loading, setLoading] = useState(true)
  const [openId, setOpenId] = useState(null)
  const { showSuccess, showError, showConfirm } = useNotification()
  const { copy } = useClipboard()

  const [eabCredentials, setEabCredentials] = useState([])
  const [eabFilterStatus, setEabFilterStatus] = useState('')
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

  useEffect(() => {
    loadCredentials()
  }, [])

  const loadCredentials = () => {
    acmeService.listEabCredentials()
      .then(res => setEabCredentials(res.data || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  const filteredEabCredentials = useMemo(() => {
    if (!eabFilterStatus) return eabCredentials
    return eabCredentials.filter(c => c.status === eabFilterStatus)
  }, [eabCredentials, eabFilterStatus])

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
      const list = await acmeService.listEabCredentials()
      setEabCredentials(list.data || [])
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
      const list = await acmeService.listEabCredentials()
      setEabCredentials(list.data || [])
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
      const list = await acmeService.listEabCredentials()
      setEabCredentials(list.data || [])
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
      const list = await acmeService.listEabCredentials()
      setEabCredentials(list.data || [])
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
      const list = await acmeService.listEabCredentials()
      setEabCredentials(list.data || [])
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

  return (
    <>
      <ListView label="EAB" caption={t('acme.eab.caption')} icon="lock" rows={filteredEabCredentials} loading={loading}
        filters={{
          views: ['', 'active', 'used', 'revoked'].map((s) => ({
            id: s, label: s ? t(`acme.eab.status${s.charAt(0).toUpperCase() + s.slice(1)}`) : t('common.all'),
            count: s ? eabCredentials.filter((c) => c.status === s).length : eabCredentials.length,
          })),
          active: eabFilterStatus, onChange: setEabFilterStatus, label: t('acme.filterByState'),
          aside: (
            <label className="checkbox-line eab-required" title={t('acme.eab.requiredDescription')}>
              <input type="checkbox" checked={!!eabRequired} disabled={!canWrite || undefined} onChange={(e) => onToggleEabRequired(e.target.checked)} />
              {t('acme.eab.requiredTitle')}
            </label>
          ),
        }}
        title={name} status={pill} openedId={openId} onOpen={(c) => setOpenId(c.id)}
        columns={[
          { id: 'kid', label: t('acme.eab.kid'), cell: (c) => <span className="mono">{c.kid}</span> },
          { id: 'domains', label: t('acme.eab.allowedDomains'), cell: (c) => <span data-testid={`eab-domains-${c.id}`}>{domainsText(c)}</span>, grow: true },
          { id: 'created', label: t('acme.eab.created'), cell: (c) => dateOf(c.created_at, locale) },
          { status: true },
        ]}
        rowActions={canDelete ? (c) => [removeAction(c)] : undefined}
        empty={eabCredentials.length ? (
          <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')} onReset={() => setEabFilterStatus('')} />
        ) : (
          <EmptyBlock id="acme-eab" icon="lock" title={t('acme.eab.empty')} text={t('acme.eab.emptyDesc')}
            action={canWrite ? { label: t('acme.eab.new'), icon: 'plus', onClick: () => setShowLocalCreate(true), primary: true } : undefined} />
        )}
        footer={{ range: t('acme.eab.totalCount', { count: filteredEabCredentials.length }) }} />
      <SlotDock>{dock}</SlotDock>

      {editingNotesId !== null && (
        <Modal open onClose={cancelEditingNotes} title={t('acme.eab.editNotesTitle')}>
          <div className="p-4 space-y-4">
            <Textarea label={t('acme.eab.notes')} aria-label={t('acme.eab.notes')} placeholder={t('acme.eab.notesPlaceholder')}
              value={editingNotesValue} onChange={(e) => setEditingNotesValue(e.target.value)} rows={3} />
            <div className="flex justify-end gap-2 pt-2 border-t border-border">
              <Button type="button" variant="secondary" onClick={cancelEditingNotes}>{t('common.cancel')}</Button>
              <Button type="button" onClick={() => saveNotes(editingNotesId)}>{t('common.save')}</Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Create EAB Credential Modal */}
      <Modal
        open={isCreateOpen}
        onClose={() => { setShowLocalCreate(false); onCloseCreateModal() }}
        title={t('acme.eab.newTitle')}
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-tertiary">
            {t('acme.eab.newDescription')}
          </p>
          <Input
            label={t('acme.eab.label')}
            placeholder={t('acme.eab.labelPlaceholder')}
            value={eabLabel}
            onChange={(e) => setEabLabel(e.target.value)}
            maxLength={255}
          />
          <Input
            label={t('acme.eab.expiresInDays')}
            type="number"
            placeholder={t('acme.eab.expiresPlaceholder')}
            value={eabExpiresInDays}
            onChange={(e) => setEabExpiresInDays(e.target.value)}
            min={1}
            helperText={t('acme.eab.expiresHelp')}
          />
          <AllowedDomainsField
            allDomains={eabAllDomains}
            onAllDomainsChange={setEabAllDomains}
            text={eabDomainsText}
            onTextChange={setEabDomainsText}
          />
          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => { setShowLocalCreate(false); onCloseCreateModal() }}>
              {t('common.cancel')}
            </Button>
            <Button type="button" onClick={handleCreateEabCredential}>
              {t('acme.eab.generate')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Show EAB Secret Once Modal */}
      <Modal
        open={!!newEabSecret}
        onClose={() => setNewEabSecret(null)}
        title={t('acme.eab.secretTitle')}
        size="md"
      >
        {newEabSecret && (
          <div className="p-4 space-y-4">
            <div className="rounded-lg border border-status-warning-op40 bg-status-warning-op10 p-3 flex gap-2">
              <Warning size={20} className="text-status-warning shrink-0 mt-0.5" weight="duotone" />
              <div className="text-sm">
                <div className="font-semibold">{t('acme.eab.secretWarningTitle')}</div>
                <div className="text-text-tertiary mt-1">{t('acme.eab.secretWarning')}</div>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">{t('acme.eab.kid')}</label>
              <div className="flex items-center gap-2">
                <code className="flex-1 px-3 py-2 rounded bg-bg-tertiary font-mono text-sm break-all">{newEabSecret.kid}</code>
                <Button type="button" variant="secondary" size="sm" onClick={() => { copy(newEabSecret.kid); showSuccess(t('acme.eab.kidCopied')) }}>
                  <Copy size={14} />
                </Button>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">{t('acme.eab.hmacKey')}</label>
              <div className="flex items-center gap-2">
                <code className="flex-1 px-3 py-2 rounded bg-bg-tertiary font-mono text-sm break-all">{newEabSecret.hmac_key}</code>
                <Button type="button" variant="secondary" size="sm" onClick={() => { copy(newEabSecret.hmac_key); showSuccess(t('acme.eab.hmacCopied')) }}>
                  <Copy size={14} />
                </Button>
              </div>
              <p className="text-xs text-text-tertiary mt-1">{t('acme.eab.hmacFormat')}</p>
            </div>
            <div className="flex justify-end pt-2 border-t border-border">
              <Button type="button" onClick={() => setNewEabSecret(null)}>
                {t('acme.eab.secretConfirm')}
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Edit allowed domains Modal */}
      <Modal
        open={!!editingDomainsCred}
        onClose={closeEditingDomains}
        title={t('acme.eab.editDomainsTitle')}
      >
        <div className="p-4 space-y-4">
          <AllowedDomainsField
            allDomains={editAllDomains}
            onAllDomainsChange={setEditAllDomains}
            text={editDomainsText}
            onTextChange={setEditDomainsText}
          />
          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button type="button" variant="secondary" onClick={closeEditingDomains}>
              {t('common.cancel')}
            </Button>
            <Button type="button" onClick={saveDomains}>
              {t('common.save')}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
