import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash, Plus } from '@phosphor-icons/react'
import { Button, Input, Select } from '../../components'

// Rows carry a stable id so editing a key neither reorders the list nor
// collides with another entry mid-typing (#222). The object shape expected
// by the API is only rebuilt on emit; duplicate keys collapse there (last
// row wins) but both rows stay visible until resolved by the user.
let nextRowId = 0
const toRows = (obj) => Object.entries(obj || {}).map(([key, val]) => ({ id: ++nextRowId, key, val }))
const toObject = (rows) => Object.fromEntries(rows.map(r => [r.key, r.val]))

export default function MappingEditor({ value, onChange, keyLabel, valueLabel, keyPlaceholder, valuePlaceholder, valueOptions }) {
  const { t } = useTranslation()
  const [rows, setRows] = useState(() => toRows(value))
  const lastEmitted = useRef(JSON.stringify(value || {}))

  // Re-sync only on external value changes (form reset, provider load) —
  // our own emits round-trip through the parent and must not rebuild rows.
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
  const addRow = () => emit([...rows, { id: ++nextRowId, key: '', val: '' }])

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_1fr_auto] gap-2 text-xs text-text-secondary">
        <span>{keyLabel}</span><span>{valueLabel}</span><span />
      </div>
      {rows.map(row => (
        <div key={row.id} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-center">
          <Input
            value={row.key}
            onChange={e => updateRow(row.id, { key: e.target.value })}
            placeholder={keyPlaceholder}
            size="sm"
          />
          {valueOptions ? (
            <Select
              value={row.val}
              onChange={val => updateRow(row.id, { val })}
              options={valueOptions}
              size="sm"
            />
          ) : (
            <Input
              value={row.val}
              onChange={e => updateRow(row.id, { val: e.target.value })}
              placeholder={valuePlaceholder}
              size="sm"
            />
          )}
          <Button type="button" size="sm" variant="ghost" onClick={() => removeRow(row.id)} aria-label={t('common.remove')}>
            <Trash size={14} className="text-status-danger" />
          </Button>
        </div>
      ))}
      <Button size="sm" variant="secondary" onClick={addRow} type="button">
        <Plus size={14} /> {t('common.add')}
      </Button>
    </div>
  )
}
