/**
 * Editable list of custom X.509 extensions (#437): OID, criticality and the DER value in hex, as
 * the issue form's `fieldset.field.full` of `.ext-row`. Rows are kept as typed; the parent builds
 * the payload with customExtensionsPayload().
 */
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './atelier/Icon'
import { FieldError } from './atelier/SettingsView'
import { customExtensionsPayload, emptyExtensionRow } from '../lib/customExtensions'

export function CustomExtensionsEditor({ rows, onChange, hint, legend, before, t: tProp }) {
  const { t: hookT } = useTranslation()
  const t = tProp || hookT
  const id = useId().replace(/:/g, '')
  const { errors } = customExtensionsPayload(rows)
  const update = (i, field, value) => onChange(rows.map((r, j) => (j === i ? { ...r, [field]: value } : r)))
  const anyCritical = rows.some(r => r.critical)

  return (
    <fieldset className="field full" data-testid="custom-extensions-editor" aria-describedby={`hint-${id}`}>
      <legend>{legend || t('customExtensions.title')}</legend>
      <small id={`hint-${id}`}>{hint || t('customExtensions.hint')}</small>
      {before}
      <div className="row-list">
        {rows.map((row, i) => {
          // The error names the input it is about: a bad OID, else a bad DER value
          const bad = errors[i] ? (errors[i] === 'customExtensions.invalidHex' ? 'value' : 'oid') : null
          const flag = (field) => (bad === field ? { 'aria-invalid': 'true', 'aria-describedby': `${id}-err-${i}` } : {})
          return (
          <div className="ext-row" key={i}>
            <label className="sr-only" htmlFor={`${id}-oid-${i}`}>{t('customExtensions.oid')}</label>
            <input id={`${id}-oid-${i}`} className="mono" value={row.oid} placeholder="1.3.6.1.4.1.99999.1" autoComplete="off" spellCheck="false"
              {...flag('oid')} onChange={(e) => update(i, 'oid', e.target.value)} />
            <label className="sr-only" htmlFor={`${id}-value-${i}`}>{t('customExtensions.value')}</label>
            <input id={`${id}-value-${i}`} className="mono" value={row.value} placeholder="0c0568656c6c6f" autoComplete="off" spellCheck="false"
              {...flag('value')} onChange={(e) => update(i, 'value', e.target.value)} />
            <label className="checkbox-line ext-critical">
              <input type="checkbox" checked={row.critical} onChange={(e) => update(i, 'critical', e.target.checked)} />
              <span>{t('customExtensions.critical')}</span>
            </label>
            <button type="button" className="icon-btn" aria-label={t('common.remove')} title={t('common.remove')} onClick={() => onChange(rows.filter((_, j) => j !== i))}>
              <Icon name="close" />
            </button>
            {errors[i] && <FieldError id={`${id}-err-${i}`} message={t(errors[i])} />}
          </div>
          )
        })}
      </div>
      {anyCritical && (
        <p className="notice warn" data-testid="custom-extensions-critical-warning">
          <Icon name="warning" /><span>{t('customExtensions.criticalWarning')}</span>
        </p>
      )}
      <button type="button" className="btn quiet add-row" onClick={() => onChange([...rows, emptyExtensionRow()])}>
        <Icon name="plus" />{t('customExtensions.add')}
      </button>
    </fieldset>
  )
}

export default CustomExtensionsEditor
