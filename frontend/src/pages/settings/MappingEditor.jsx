import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash, Plus } from '@phosphor-icons/react'
import { Button, Input, Select } from '../../components'

// Rows carry a stable id so editing a key neither reorders the list nor
// collides with another entry mid-typing (#222). The object shape expected
// by the API is only rebuilt on emit, where a repeated key keeps its first row: every
// later row of a key is marked invalid, which blocks a submit only inside a <form>.
let nextRowId = 0
const toRows = (obj) => Object.entries(obj || {}).map(([key, val]) => ({ id: ++nextRowId, key, val }))
const toObject = (rows) => {
  const seen = new Set()
  return Object.fromEntries(rows.filter(r => !seen.has(r.key) && seen.add(r.key)).map(r => [r.key, r.val]))
}

// Ids of the rows whose non-empty key an earlier row already holds
const repeatedRows = (rows) => {
  const seen = new Set()
  const repeated = new Set()
  for (const r of rows) {
    if (r.key && seen.has(r.key)) repeated.add(r.id)
    seen.add(r.key)
  }
  return repeated
}

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
  const repeated = repeatedRows(rows)

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_1fr_auto] gap-2 text-xs text-text-secondary">
        <span>{keyLabel}</span><span>{valueLabel}</span><span />
      </div>
      {rows.map(row => {
        const duplicate = repeated.has(row.id) ? t('common.duplicateKey', { key: row.key }) : ''
        return (
        <div key={row.id} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-start">
          <Input
            ref={el => el?.setCustomValidity(duplicate)}
            value={row.key}
            onChange={e => updateRow(row.id, { key: e.target.value })}
            placeholder={keyPlaceholder}
            error={duplicate || undefined}
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
        )
      })}
      <Button size="sm" variant="secondary" onClick={addRow} type="button">
        <Plus size={14} /> {t('common.add')}
      </Button>
    </div>
  )
}
