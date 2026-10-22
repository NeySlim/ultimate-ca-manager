import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash, Plus } from '@phosphor-icons/react'
import { Button, Input, Select } from '../../components'

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
const toObject = (rows) => Object.fromEntries(rows.map(r => [r.key, serializeRoleEntry(r)]))

export default function RoleMappingEditor({ value, onChange, keyLabel, keyPlaceholder, roleOptions = [], customRoles = [] }) {
  const { t } = useTranslation()
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

  const none = { value: '', label: t('common.none') }
  const baseOptions = [none, ...roleOptions]
  // A custom role already in the mapping stays visible even if the list lacks it
  const customOptionsFor = (current) => {
    const names = current && !customRoles.includes(current) ? [...customRoles, current] : customRoles
    return [none, ...names.map(n => ({ value: n, label: n }))]
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 text-xs text-text-secondary">
        <span>{keyLabel}</span><span>{t('sso.baseRole')}</span><span>{t('sso.customRole')}</span><span />
      </div>
      {rows.map(row => (
        <div key={row.id} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 items-center">
          <Input
            value={row.key}
            onChange={e => updateRow(row.id, { key: e.target.value })}
            placeholder={keyPlaceholder}
            size="sm"
          />
          <Select value={row.role} onChange={role => updateRow(row.id, { role })} options={baseOptions} size="sm" />
          <Select value={row.custom} onChange={custom => updateRow(row.id, { custom })} options={customOptionsFor(row.custom)} size="sm" />
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
