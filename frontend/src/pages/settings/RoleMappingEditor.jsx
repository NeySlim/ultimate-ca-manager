import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../../components/atelier/Icon'
import { FieldError } from '../../components/atelier/SettingsView'

// A stored entry is a base-role string or {role, custom_role}. The string
// form is kept whenever no custom role is chosen, so old payloads round-trip.
export const normalizeRoleEntry = (v) => {
  if (v && typeof v === 'object') return { role: v.role || '', custom: v.custom_role || '' }
  return { role: v || '', custom: '' }
}

export const serializeRoleEntry = ({ role, custom }) => {
  if (custom) return { role: role || null, custom_role: custom }
  return role || ''
}

let nextRowId = 0
const toRows = (obj) => Object.entries(obj || {}).map(([key, val]) => ({ id: ++nextRowId, key, ...normalizeRoleEntry(val) }))
// A repeated key keeps its first row; every later row of it is marked invalid (blocks a submit inside a <form>)
const toObject = (rows) => {
  const seen = new Set()
  return Object.fromEntries(rows.filter(r => !seen.has(r.key) && seen.add(r.key)).map(r => [r.key, serializeRoleEntry(r)]))
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
 * External group → base role and custom role, as MappingEditor's rows with a fourth column
 * (`.ext-row.role-row`); the column names head the rows, each control is named by its row.
 */
export default function RoleMappingEditor({ value, onChange, legend, hint, keyLabel, keyPlaceholder, roleOptions = [], customRoles = [] }) {
  const { t } = useTranslation()
  const uid = useId().replace(/:/g, '')
  const [rows, setRows] = useState(() => toRows(value))
  const lastEmitted = useRef(JSON.stringify(value || {}))

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
  const addRow = () => emit([...rows, { id: ++nextRowId, key: '', role: '', custom: '' }])

  const repeated = repeatedRows(rows)

  const none = { value: '', label: t('common.none') }
  const baseOptions = [none, ...roleOptions]
  // A custom role already in the mapping stays visible even if the list lacks it
  const customOptionsFor = (current) => {
    const names = current && !customRoles.includes(current) ? [...customRoles, current] : customRoles
    return [none, ...names.map(n => ({ value: n, label: n }))]
  }
  const options = (list) => list.map(o => <option key={o.value} value={o.value}>{o.label}</option>)

  return (
    <fieldset className="field full" aria-describedby={hint ? `hint-${uid}` : undefined}>
      {legend && <legend>{legend}</legend>}
      {hint && <small id={`hint-${uid}`}>{hint}</small>}
      <div className="row-list">
        {rows.length > 0 && (
          <div className="ext-row role-row row-head" aria-hidden="true">
            <span>{keyLabel}</span><span>{t('sso.baseRole')}</span><span>{t('sso.customRole')}</span><span />
          </div>
        )}
        {rows.map((row, i) => {
          const duplicate = repeated.has(row.id) ? t('common.duplicateKey', { key: row.key }) : ''
          const id = `${uid}-${row.id}`
          return (
            <div key={row.id} className="ext-row role-row">
              <label className="sr-only" htmlFor={`${id}-key`}>{`${keyLabel} ${i + 1}`}</label>
              <input id={`${id}-key`} name="extOid" ref={el => el?.setCustomValidity(duplicate)} value={row.key} placeholder={keyPlaceholder}
                autoComplete="off" spellCheck={false} aria-invalid={duplicate ? 'true' : undefined}
                aria-describedby={duplicate ? `err-${id}-key` : undefined}
                onChange={e => updateRow(row.id, { key: e.target.value })} />
              <label className="sr-only" htmlFor={`${id}-role`}>{`${t('sso.baseRole')} ${i + 1}`}</label>
              <select id={`${id}-role`} value={row.role} onChange={e => updateRow(row.id, { role: e.target.value })}>{options(baseOptions)}</select>
              <label className="sr-only" htmlFor={`${id}-custom`}>{`${t('sso.customRole')} ${i + 1}`}</label>
              <select id={`${id}-custom`} value={row.custom} onChange={e => updateRow(row.id, { custom: e.target.value })}>{options(customOptionsFor(row.custom))}</select>
              <button type="button" className="icon-btn" aria-label={t('common.remove')} title={t('common.remove')} onClick={() => removeRow(row.id)}>
                <Icon name="close" />
              </button>
              {duplicate && <FieldError id={`err-${id}-key`} message={duplicate} />}
            </div>
          )
        })}
      </div>
      <button type="button" className="btn quiet add-row" onClick={addRow}><Icon name="plus" />{t('common.add')}</button>
    </fieldset>
  )
}
