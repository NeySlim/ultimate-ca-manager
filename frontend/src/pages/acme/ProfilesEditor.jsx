import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon, IconBtn } from '../../components/atelier'

/**
 * Editor for ACME certificate profiles (draft-ietf-acme-profiles).
 *
 * The API stores a map {name: {description, validity_days, digest, template_id}};
 * rows carry
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
  template_id: spec?.template_id ? String(spec.template_id) : '',
}))

const toObject = (rows) => Object.fromEntries(rows.map(r => [r.name, {
  description: r.description,
  validity_days: Number(r.validity_days) || 90,
  digest: r.digest,
  // A bound template's KU/EKU govern issuance under the profile; null = none
  template_id: Number(r.template_id) || null,
}]))

const DIGESTS = ['sha256', 'sha384', 'sha512']

export default function ProfilesEditor({ value, onChange, disabled, templates = [], saved = {} }) {
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
    id: ++nextRowId, name: '', description: '', validity_days: 90, digest: 'sha256', template_id: '',
  }])

  // A deactivated template is refused on a new binding: offered only under the name the server has it bound to,
  // and kept visible, marked, on a row that still carries it
  const templateOptions = (row) => [
    { value: '', label: t('acme.noTemplate') },
    ...templates.filter(tpl => tpl.is_active !== false || String(tpl.id) === row.template_id
      || String(tpl.id) === String(saved[row.name]?.template_id ?? ''))
      .map(tpl => ({ value: String(tpl.id), label: tpl.is_active === false ? `${tpl.name} (${t('common.inactive')})` : tpl.name })),
  ]

  // One row per profile, in the mockup's row list (inputs, then the remove button), labelled for screen readers
  return (
    <div className="profiles-editor">
      <div className="row-list">
        {rows.map((row, i) => (
          <div key={row.id} className="profile-row">
            <label className="sr-only" htmlFor={`acme-profile-name-${i}`}>{t('acme.profileName')} {i + 1}</label>
            <input id={`acme-profile-name-${i}`} value={row.name} placeholder={t('acme.profileNamePlaceholder')} disabled={disabled || undefined}
              onChange={(e) => updateRow(row.id, { name: e.target.value })} />
            <label className="sr-only" htmlFor={`acme-profile-desc-${i}`}>{t('common.description')} {i + 1}</label>
            <input id={`acme-profile-desc-${i}`} value={row.description} placeholder={t('acme.profileDescriptionPlaceholder')} disabled={disabled || undefined}
              onChange={(e) => updateRow(row.id, { description: e.target.value })} />
            <label className="sr-only" htmlFor={`acme-profile-days-${i}`}>{t('acme.profileValidity')} {i + 1}</label>
            <input id={`acme-profile-days-${i}`} type="number" min="1" max="3650" value={row.validity_days} disabled={disabled || undefined}
              onChange={(e) => updateRow(row.id, { validity_days: e.target.value })} />
            <label className="sr-only" htmlFor={`acme-profile-digest-${i}`}>{t('acme.profileDigest')} {i + 1}</label>
            <select id={`acme-profile-digest-${i}`} value={row.digest} disabled={disabled || undefined} onChange={(e) => updateRow(row.id, { digest: e.target.value })}>
              {DIGESTS.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <label className="sr-only" htmlFor={`acme-profile-template-${i}`}>{t('acme.profileTemplate')} {i + 1}</label>
            <select id={`acme-profile-template-${i}`} value={row.template_id} disabled={disabled || undefined} onChange={(e) => updateRow(row.id, { template_id: e.target.value })}>
              {templateOptions(row).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <IconBtn icon="close" label={t('acme.removeProfile', { name: row.name || i + 1 })} disabled={disabled || undefined} onClick={() => removeRow(row.id)} />
          </div>
        ))}
      </div>
      <button type="button" className="btn quiet add-row" onClick={addRow} disabled={disabled || undefined}>
        <Icon name="plus" />{t('acme.addProfile')}
      </button>
    </div>
  )
}
