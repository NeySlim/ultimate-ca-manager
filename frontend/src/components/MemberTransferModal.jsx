/**
 * The members of a group in the mockup's dialog: the palette's search, then one `.checkbox-line`
 * per user in a `.columns-list` (ticked = member), a line that ticks or clears the users shown,
 * and Save once the set differs from the group's. onSave receives the member user ids.
 */
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from './atelier/AtelierDialog'
import { Btn } from './atelier/Btn'
import { Icon } from './atelier/Icon'

// A member arrives as the user ({ id }) or as the membership ({ user_id })
const memberId = (m) => m.id ?? m.user_id

const matches = (u, q) => !q || [u.username, u.email, u.full_name].some((v) => v?.toLowerCase().includes(q))

export function MemberTransferModal({ open, ...props }) {
  return open ? <MembersDialog {...props} /> : null
}

function MembersDialog({ onClose, title, allUsers = [], currentMembers = [], onSave, loading = false }) {
  const { t } = useTranslation()
  const original = useMemo(() => new Set(currentMembers.map(memberId)), [currentMembers])
  const [members, setMembers] = useState(() => new Set(original))
  const [search, setSearch] = useState('')
  const q = search.trim().toLowerCase()
  const shown = allUsers.filter((u) => matches(u, q))
  const allShown = shown.length > 0 && shown.every((u) => members.has(u.id))
  const changed = members.size !== original.size || [...members].some((id) => !original.has(id))

  const toggle = (id, on) => setMembers((prev) => {
    const next = new Set(prev)
    if (on) next.add(id)
    else next.delete(id)
    return next
  })
  const toggleShown = (on) => setMembers((prev) => {
    const next = new Set(prev)
    for (const u of shown) {
      if (on) next.add(u.id)
      else next.delete(u.id)
    }
    return next
  })
  const close = () => { if (!loading) onClose?.() }

  return (
    <AtelierDialog title={title || t('members.manageMembers')} size="narrow" onClose={close} testId="group-members-dialog">
      <div className="command-search">
        <Icon name="search" />
        <input type="search" data-autofocus aria-label={t('common.search')} placeholder={`${t('common.search')}…`}
          value={search} autoComplete="off" spellCheck={false} onChange={(e) => setSearch(e.target.value)} />
      </div>
      {shown.length === 0 ? (
        <p className="event-detail">{t('members.noMatchingUsers')}</p>
      ) : (
        <div className="columns-list" style={{ maxHeight: '45dvh', overflow: 'auto' }}>
          <label className="checkbox-line">
            <input type="checkbox" checked={allShown} onChange={(e) => toggleShown(e.target.checked)} />
            {t('common.selectAll')} ({shown.filter((u) => members.has(u.id)).length}/{shown.length})
          </label>
          {shown.map((u) => (
            <label key={u.id} className="checkbox-line">
              <input type="checkbox" checked={members.has(u.id)} onChange={(e) => toggle(u.id, e.target.checked)} />
              <span style={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}>
                {u.username}{u.email && <span className="muted"> · {u.email}</span>}
              </span>
            </label>
          ))}
        </div>
      )}
      <div className="modal-actions">
        {changed && <span className="muted small" style={{ marginRight: 'auto' }}>{t('common.unsavedChanges')}</span>}
        <button type="button" className="btn" data-action="close-modal" disabled={loading || undefined} onClick={close}>{t('common.cancel')}</button>
        <Btn tone="primary" icon="check" disabled={!changed || loading || undefined} onClick={() => onSave?.([...members])}>
          {loading ? t('common.saving') : t('common.save')}
        </Btn>
      </div>
    </AtelierDialog>
  )
}

export default MemberTransferModal
