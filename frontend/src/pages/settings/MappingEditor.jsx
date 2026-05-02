import { useTranslation } from 'react-i18next'
import { Trash, Plus } from '@phosphor-icons/react'
import { Button, Input, Select } from '../../components'

export default function MappingEditor({ value, onChange, keyLabel, valueLabel, keyPlaceholder, valuePlaceholder, valueOptions }) {
  const { t } = useTranslation()
  const entries = Object.entries(value || {})

  const updateEntry = (oldKey, newKey, newVal) => {
    const updated = { ...value }
    if (oldKey !== newKey) delete updated[oldKey]
    updated[newKey] = newVal
    onChange(updated)
  }
  const removeEntry = (key) => {
    const updated = { ...value }
    delete updated[key]
    onChange(updated)
  }
  const addEntry = () => {
    onChange({ ...value, '': '' })
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_1fr_auto] gap-2 text-xs text-text-secondary">
        <span>{keyLabel}</span><span>{valueLabel}</span><span />
      </div>
      {entries.map(([k, v], idx) => (
        <div key={idx} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-center">
          <Input
            value={k}
            onChange={e => updateEntry(k, e.target.value, v)}
            placeholder={keyPlaceholder}
            size="sm"
          />
          {valueOptions ? (
            <Select
              value={v}
              onChange={val => updateEntry(k, k, val)}
              options={valueOptions}
              size="sm"
            />
          ) : (
            <Input
              value={v}
              onChange={e => updateEntry(k, k, e.target.value)}
              placeholder={valuePlaceholder}
              size="sm"
            />
          )}
          <Button type="button" size="sm" variant="ghost" onClick={() => removeEntry(k)} aria-label={t('common.remove')}>
            <Trash size={14} className="text-status-danger" />
          </Button>
        </div>
      ))}
      <Button size="sm" variant="secondary" onClick={addEntry} type="button">
        <Plus size={14} /> {t('common.add')}
      </Button>
    </div>
  )
}
