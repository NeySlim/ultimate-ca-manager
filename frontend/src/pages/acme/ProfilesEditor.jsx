import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash, Plus } from '@phosphor-icons/react'
import { Button, Input, Select } from '../../components'

/**
 * Editor for ACME certificate profiles (draft-ietf-acme-profiles).
 *
 * The API stores a map {name: {description, validity_days, digest}}; rows carry
 * a stable id so editing a profile name neither reorders the list nor collides
 * with another entry mid-typing (same approach as MappingEditor, see #222).
 * The map is only rebuilt on emit — duplicate names collapse there (last row
 * wins) while both rows stay visible until the user resolves it.
 */
let nextRowId = 0

const toRows = (obj) => Object.entries(obj || {}).map(([name, spec]) => ({
  id: ++nextRowId,
  name,
  description: spec?.description ?? '',
  validity_days: spec?.validity_days ?? 90,
  digest: spec?.digest ?? 'sha256',
}))

const toObject = (rows) => Object.fromEntries(rows.map(r => [r.name, {
  description: r.description,
  validity_days: Number(r.validity_days) || 90,
  digest: r.digest,
}]))

const DIGESTS = ['sha256', 'sha384', 'sha512']

export default function ProfilesEditor({ value, onChange, disabled }) {
  const { t } = useTranslation()
  const [rows, setRows] = useState(() => toRows(value))
  const lastEmitted = useRef(JSON.stringify(value || {}))

  // Re-sync only on external changes (settings reload) — our own emits
  // round-trip through the parent and must not rebuild the rows.
  useEffect(() => {
    const incoming = JSON.stringify(value || {})
    if (incoming !== lastEmitted.current) {
      lastEmitted.current = incoming
      setRows(toRows(value))
    }
  }, [value])

  const emit = (next) => {
    setRows(next)
    const obj = toObject(next)
    lastEmitted.current = JSON.stringify(obj)
    onChange(obj)
  }

  const updateRow = (id, patch) => emit(rows.map(r => (r.id === id ? { ...r, ...patch } : r)))
  const removeRow = (id) => emit(rows.filter(r => r.id !== id))
  const addRow = () => emit([...rows, {
    id: ++nextRowId, name: '', description: '', validity_days: 90, digest: 'sha256',
  }])

  return (
    <div className="space-y-2">
      {rows.length > 0 && (
        <div className="grid grid-cols-[1fr_1.4fr_90px_110px_auto] gap-2 text-xs text-text-secondary">
          <span>{t('acme.profileName')}</span>
          <span>{t('common.description')}</span>
          <span>{t('acme.profileValidity')}</span>
          <span>{t('acme.profileDigest')}</span>
          <span />
        </div>
      )}
      {rows.map(row => (
        <div key={row.id} className="grid grid-cols-[1fr_1.4fr_90px_110px_auto] gap-2 items-center">
          <Input
            value={row.name}
            onChange={(e) => updateRow(row.id, { name: e.target.value })}
            placeholder={t('acme.profileNamePlaceholder')}
            disabled={disabled}
          />
          <Input
            value={row.description}
            onChange={(e) => updateRow(row.id, { description: e.target.value })}
            placeholder={t('acme.profileDescriptionPlaceholder')}
            disabled={disabled}
          />
          <Input
            type="number"
            min="1"
            max="3650"
            value={row.validity_days}
            onChange={(e) => updateRow(row.id, { validity_days: e.target.value })}
            disabled={disabled}
          />
          <Select
            options={DIGESTS.map(d => ({ value: d, label: d }))}
            value={row.digest}
            onChange={(val) => updateRow(row.id, { digest: val })}
            disabled={disabled}
          />
          <Button
            type="button"
            variant="danger-soft"
            size="xs"
            onClick={() => removeRow(row.id)}
            disabled={disabled}
            aria-label={t('common.delete')}
          >
            <Trash size={14} />
          </Button>
        </div>
      ))}
      <Button type="button" variant="secondary" size="xs" onClick={addRow} disabled={disabled}>
        <Plus size={14} /> {t('acme.addProfile')}
      </Button>
    </div>
  )
}
