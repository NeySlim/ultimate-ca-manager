/**
 * Editable list of custom X.509 extensions (#437): OID, criticality and the
 * DER value in hex. Rows are kept as typed; the parent builds the payload
 * with customExtensionsPayload().
 */
import { useTranslation } from 'react-i18next'
import { Plus, Trash, Warning } from '@phosphor-icons/react'
import { Button } from './Button'
import { Input } from './Input'
import { customExtensionsPayload, emptyExtensionRow } from '../lib/customExtensions'

export function CustomExtensionsEditor({ rows, onChange, hint, t: tProp }) {
  const { t: hookT } = useTranslation()
  const t = tProp || hookT
  const { errors } = customExtensionsPayload(rows)
  const update = (i, field, value) => onChange(rows.map((r, j) => (j === i ? { ...r, [field]: value } : r)))
  const anyCritical = rows.some(r => r.critical)

  return (
    <div className="space-y-2" data-testid="custom-extensions-editor">
      <p className="text-xs text-text-secondary">{hint || t('customExtensions.hint')}</p>
      {rows.map((row, i) => (
        <div key={i} className="space-y-1">
          <div className="grid grid-cols-[minmax(0,12rem)_minmax(0,1fr)_auto_auto] gap-2 items-end">
            <Input
              label={t('customExtensions.oid')}
              value={row.oid}
              onChange={(e) => update(i, 'oid', e.target.value)}
              placeholder="1.3.6.1.4.1.99999.1"
              className="font-mono"
            />
            <Input
              label={t('customExtensions.value')}
              value={row.value}
              onChange={(e) => update(i, 'value', e.target.value)}
              placeholder="0c0568656c6c6f"
              className="font-mono"
            />
            <label className="flex items-center gap-1.5 text-sm text-text-primary cursor-pointer select-none pb-2">
              <input
                type="checkbox"
                checked={row.critical}
                onChange={(e) => update(i, 'critical', e.target.checked)}
                className="accent-accent-primary"
                aria-label={t('customExtensions.critical')}
              />
              {t('customExtensions.critical')}
            </label>
            <Button type="button" size="sm" variant="secondary" onClick={() => onChange(rows.filter((_, j) => j !== i))}
              aria-label={t('common.remove')} title={t('common.remove')}>
              <Trash size={14} />
            </Button>
          </div>
          {errors[i] && <p className="text-xs text-status-danger" role="alert">{t(errors[i])}</p>}
        </div>
      ))}
      {anyCritical && (
        <div className="p-3 rounded-lg border border-yellow-500/30 bg-yellow-500/10 flex items-start gap-2 text-xs text-text-secondary"
          data-testid="custom-extensions-critical-warning">
          <Warning size={16} className="text-yellow-500 shrink-0 mt-0.5" weight="bold" />
          <span>{t('customExtensions.criticalWarning')}</span>
        </div>
      )}
      <Button type="button" size="sm" variant="secondary" onClick={() => onChange([...rows, emptyExtensionRow()])}>
        <Plus size={14} />
        {t('customExtensions.add')}
      </Button>
    </div>
  )
}
