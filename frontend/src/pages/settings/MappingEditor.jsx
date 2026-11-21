import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../../components/atelier/Icon'
import { FieldError } from '../../components/atelier/SettingsView'

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

/**
 * Key/value rows as the issue form's extension rows (`fieldset.field.full`, `.row-list` of
 * `.ext-row`, « Ajouter » under them; `fixed` keeps the mockup's three columns); each control is named by its column and its row.
 */
export default function MappingEditor({ value, onChange, legend, hint, keyLabel, valueLabel, keyPlaceholder, valuePlaceholder, valueOptions }) {
  const { t } = useTranslation()
  const uid = useId().replace(/:/g, '')
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
    <fieldset className="field full" aria-describedby={hint ? `hint-${uid}` : undefined}>
      {legend && <legend>{legend}</legend>}
      {hint && <small id={`hint-${uid}`}>{hint}</small>}
      <div className="row-list">
        {rows.map((row, i) => {
          const duplicate = repeated.has(row.id) ? t('common.duplicateKey', { key: row.key }) : ''
          const kid = `${uid}-key-${row.id}`
          const vid = `${uid}-val-${row.id}`
          return (
            <div key={row.id} className="ext-row fixed">
              <label className="sr-only" htmlFor={kid}>{`${keyLabel} ${i + 1}`}</label>
              <input id={kid} name="extOid" ref={el => el?.setCustomValidity(duplicate)} value={row.key} placeholder={keyPlaceholder}
                autoComplete="off" spellCheck={false} aria-invalid={duplicate ? 'true' : undefined}
                aria-describedby={duplicate ? `err-${kid}` : undefined}
                onChange={e => updateRow(row.id, { key: e.target.value })} />
              <label className="sr-only" htmlFor={vid}>{`${valueLabel} ${i + 1}`}</label>
              {valueOptions ? (
                <select id={vid} name="extValue" value={row.val} onChange={e => updateRow(row.id, { val: e.target.value })}>
                  {valueOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              ) : (
                <input id={vid} name="extValue" value={row.val} placeholder={valuePlaceholder} autoComplete="off" spellCheck={false}
                  onChange={e => updateRow(row.id, { val: e.target.value })} />
              )}
              <button type="button" className="icon-btn" aria-label={t('common.remove')} title={t('common.remove')} onClick={() => removeRow(row.id)}>
                <Icon name="close" />
              </button>
              {duplicate && <FieldError id={`err-${kid}`} message={duplicate} />}
            </div>
          )
        })}
      </div>
      <button type="button" className="btn quiet add-row" onClick={addRow}><Icon name="plus" />{t('common.add')}</button>
    </fieldset>
  )
}
