/**
 * The mockup's settingsView(), the configuration form of the module pages: the table of contents
 * (each section marked « Modifié » or « À corriger »), a select to jump to a section on a phone,
 * one frame per section with its groups of fields and an optional test, the sticky save bar, then
 * the history of changes. The page holds the draft: every change comes back through `onChange`,
 * and the marks, the state sentence and the save buttons follow it without a reload.
 */
import { Component } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'
import { jumpTo } from './helpers'

/** A field's error under it: the warning icon and the words, named by aria-describedby. */
export function FieldError({ id, message }) {
  return <p className="field-error" id={id}><Icon name="warning" /><span>{message}</span></p>
}

const keysOf = (s) => s.groups.flatMap((g) => g.fields).filter((f) => !f.readonly).map((f) => f.key)

/**
 * One field: a checkbox line, a read-only value, a select, or a text input, with its hint and
 * its error. field: { key, label, hint, checkbox, readonly, options: [[value, label]], short, wide, numeric }
 */
export function SettingsField({ field: f, value, error, onChange }) {
  const id = `set-${f.key}`
  const ids = [f.hint && `hint-${id}`, error && `err-${id}`].filter(Boolean).join(' ') || undefined
  const hint = f.hint ? <small id={`hint-${id}`}>{f.hint}</small> : null
  if (f.checkbox) {
    return (
      <label className="checkbox-line field full">
        <input type="checkbox" id={id} data-setting={f.key} checked={!!value} onChange={(e) => onChange(f.key, e.target.checked)} />{f.label}
      </label>
    )
  }
  if (f.readonly) {
    return <div className="field full"><label htmlFor={id}>{f.label}</label><input id={id} value={f.readonly} readOnly aria-describedby={ids} />{hint}</div>
  }
  if (f.options) {
    return (
      <div className={f.short ? 'field short' : 'field'}>
        <label htmlFor={id}>{f.label}</label>
        <select id={id} data-setting={f.key} value={value ?? ''} aria-describedby={ids} aria-invalid={error ? 'true' : undefined} onChange={(e) => onChange(f.key, e.target.value)}>
          {f.options.map(([o, l]) => <option key={o} value={o}>{l}</option>)}
        </select>
        {hint}
      </div>
    )
  }
  return (
    <div className={['field', f.wide ? 'full' : f.short ? 'short' : ''].join(' ')}>
      <label htmlFor={id}>{f.label}</label>
      <input id={id} data-setting={f.key} value={value ?? ''} inputMode={f.numeric ? 'numeric' : undefined} autoComplete="off" spellCheck={false}
        aria-describedby={ids} aria-invalid={error ? 'true' : undefined} onChange={(e) => onChange(f.key, e.target.value)} />
      {hint}
      {error && <FieldError id={`err-${id}`} message={error} />}
    </div>
  )
}

/** One section that fails to render leaves the others on the page. */
class SectionBoundary extends Component {
  constructor(props) { super(props); this.state = { failed: false } }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

/**
 * A section: its heading, its groups (a fieldset per legend), its test.
 * test: { label, onTest, result: { ok, text } | null, hint, busy }
 */
export function SettingsSection({ section: s, values, errors, onChange }) {
  const { t } = useTranslation()
  const r = s.test?.result
  return (
    <section className="panel settings-section" id={`set-sec-${s.id}`} aria-labelledby={`set-title-${s.id}`}>
      <header className="panel-heading">
        <div>
          <h2 id={`set-title-${s.id}`} tabIndex={-1}>{s.label}</h2>
          {s.desc && <p>{s.desc}</p>}
          {s.error && <p className="field-error" role="alert"><Icon name="warning" /><span>{s.error}</span></p>}
        </div>
      </header>
      <div className="settings-body">
        <SectionBoundary fallback={<p className="field-error" role="alert"><Icon name="warning" /><span>{t('sectioned.sectionFailed')}</span></p>}>
          {s.groups.map((g) => (
            <fieldset key={g.legend} className="settings-group">
              <legend>{g.legend}</legend>
              <div className="settings-grid">
                {g.fields.map((f) => (
                  <SettingsField key={f.key} field={f} value={values[f.key]} error={errors[f.key]} onChange={onChange} />
                ))}
              </div>
            </fieldset>
          ))}
          {s.children}
          {s.test && (
            <div className="settings-test">
              <button type="button" className="btn" id={`test-${s.id}`} data-settings-test={s.id} data-write="" disabled={s.test.busy || undefined} onClick={s.test.onTest}>
                <Icon name="send" />{s.test.label}
              </button>
              {r ? (
                <p className={`test-result ${r.ok ? 'good' : 'bad'}`} id={`test-result-${s.id}`}><Icon name={r.ok ? 'check' : 'warning'} /><span>{r.text}</span></p>
              ) : (
                <p className="test-result muted" id={`test-result-${s.id}`}><Icon name="help" /><span>{s.test.hint}</span></p>
              )}
            </div>
          )}
        </SectionBoundary>
      </div>
    </section>
  )
}

/** The table of contents: a link per section, marked « À corriger » or « Modifié »; `current` is the shown one. */
export function SettingsToc({ sections, flags, current, label, onJump }) {
  const { t } = useTranslation()
  return (
    <nav className="settings-toc" id="settings-toc" aria-label={label}>
      <ul>
        {sections.map((s) => (
          <li key={s.id}>
            <a href={`#set-sec-${s.id}`} data-jump={s.id} aria-current={current === s.id ? 'true' : undefined}
              onClick={(e) => {
                if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
                e.preventDefault()
                jumpTo(s.id)
                onJump?.(s.id)
              }}>
              <Icon name={s.icon} /><span>{s.label}</span>
              {flags[s.id] === 'error' ? <span className="toc-flag bad"><Icon name="warning" />{t('sectioned.flagError')}</span>
                : flags[s.id] === 'modified' ? <span className="toc-flag">{t('sectioned.flagModified')}</span> : null}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}

/**
 * @param {object} p
 * @param {Array} p.sections  { id, label, icon, desc, groups: [{ legend, fields }], test?, error?, children? }
 * @param {object} p.values  the draft, field by field
 * @param {object} p.errors  field key -> message
 * @param {string[]} p.changed  keys of the fields changed against the saved values
 * @param {(key, value) => void} p.onChange
 * @param {() => void} p.onSave  the form's submit (Enregistrer)
 * @param {() => void} p.onReset  Annuler les modifications
 * @param {{ at, by }} [p.lastSaved]
 * @param {string[]} [p.failed]  sections whose save failed
 * @param {string} [p.announce]  the polite announcement after a save or a refusal
 * @param {{ title, text, children }} [p.history]
 * @param {import('react').Ref} [p.stateRef]  takes the focus after a save or a reset
 * @param {string} [p.current]  the section shown (a link that names one); `onJump` hears each jump, to keep it in the address
 */
export function SettingsView({ sections, values, errors = {}, changed = [], onChange, onSave, onReset, lastSaved, saving = false, failed = [], announce = '', history, stateRef, current, tocLabel, onJump }) {
  const { t } = useTranslation()
  const dirty = changed.length > 0
  const labelOf = Object.fromEntries(sections.flatMap((s) => s.groups.flatMap((g) => g.fields)).map((f) => [f.key, f.label]))
  const flags = Object.fromEntries(sections.map((s) => {
    const keys = keysOf(s)
    return [s.id, keys.some((k) => errors[k]) || s.error ? 'error' : keys.some((k) => changed.includes(k)) ? 'modified' : '']
  }))
  const state = failed.length ? (
    <><Icon name="warning" /><span><strong>{t('sectioned.saveFailedTitle')}</strong>{t('sectioned.saveFailedIn', { sections: failed.join(', ') })}</span></>
  ) : dirty ? (
    <><Icon name="warning" /><span><strong>{t('sectioned.pendingTitle')}</strong>{t('sectioned.pendingFields', { fields: changed.map((k) => labelOf[k] || k).join(', ') })}</span></>
  ) : (
    <><Icon name="check" /><span>{t('sectioned.nothingPending')}{lastSaved && <>{' '}{lastSaved.by
      ? t('sectioned.lastSavedBy', { date: lastSaved.at, user: lastSaved.by }) : t('sectioned.lastSaved', { date: lastSaved.at })}</>}</span></>
  )
  return (
    <div className="scroll-view" id="view-scroll">
      <div className="settings-layout">
        <SettingsToc sections={sections} flags={flags} current={current} label={tocLabel} onJump={onJump} />
        <div className="settings-main">
          <form className="settings-form" id="settings-form" noValidate onSubmit={(e) => { e.preventDefault(); onSave?.() }}>
            <div className="field settings-jump">
              <label htmlFor="settings-jump">{t('sectioned.jumpLabel')}</label>
              <select id="settings-jump" value={current || sections[0]?.id} onChange={(e) => { jumpTo(e.target.value); onJump?.(e.target.value) }}>
                {sections.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
            </div>
            {sections.map((s) => <SettingsSection key={s.id} section={s} values={values} errors={errors} onChange={onChange} />)}
            <div className={dirty ? 'settings-savebar dirty' : 'settings-savebar'} id="settings-savebar">
              <p className="settings-state" id="settings-state" tabIndex={-1} ref={stateRef}>{state}</p>
              <button type="button" className="btn" id="settings-reset" data-action="settings-reset" disabled={!dirty || saving} onClick={onReset}>{t('sectioned.undo')}</button>
              <button type="submit" className="btn primary" id="settings-save" disabled={!dirty || saving}><Icon name="check" />{saving ? t('sectioned.saving') : t('common.save')}</button>
            </div>
            <p className="sr-only" id="settings-announce" role="status" aria-live="polite">{announce}</p>
          </form>
          {history && (
            <section className="panel settings-history" aria-labelledby="set-history-title">
              <header className="panel-heading"><div><h2 id="set-history-title">{history.title}</h2>{history.text && <p>{history.text}</p>}</div></header>
              <div className="panel-content">{history.children}</div>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}

export default SettingsView
