/**
 * The mockup's settingsView(), in pieces a page composes: the layout (table of contents beside the
 * main column), the jump select of a phone, one frame per section, its groups of fields, a test,
 * the sticky save bar and the history of changes. The layout's column is a `div.settings-form`
 * when the sections hold forms of their own (a form cannot nest one), a `<form>` otherwise.
 * SettingsView draws the whole form from data, as the mockup's settingsFields does.
 */
import { Component, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'
import { jumpTo } from './helpers'

/** A field's error under it: the warning icon and the words, named by aria-describedby. */
export function FieldError({ id, message }) {
  return <p className="field-error" id={id}><Icon name="warning" /><span>{message}</span></p>
}

// A section's own control that is not a field (a list of rows) names its key in extraKeys: [[key, label]]
const keysOf = (s) => [...s.groups.flatMap((g) => g.fields).filter((f) => !f.readonly).map((f) => f.key), ...(s.extraKeys || []).map(([k]) => k)]

/**
 * One field: a checkbox line, a read-only value, a select, or a text input, with its hint and
 * its error. field: { key, label, hint, checkbox, readonly, options: [[value, label]], short, wide, numeric,
 * disabled, type (an input's type, e.g. password), placeholder }
 */
export function SettingsField({ field: f, value, error, onChange }) {
  const id = `set-${f.key}`
  const ids = [f.hint && `hint-${id}`, error && `err-${id}`].filter(Boolean).join(' ') || undefined
  const hint = f.hint ? <small id={`hint-${id}`}>{f.hint}</small> : null
  if (f.checkbox) {
    const box = <input type="checkbox" id={id} data-setting={f.key} checked={!!value} disabled={f.disabled || undefined} aria-describedby={ids}
      onChange={(e) => onChange(f.key, e.target.checked)} />
    // The mockup's checkbox has no hint; one that has keeps it under the line, in the same cell
    if (f.hint) return <div className="field full"><label className="checkbox-line">{box}{f.label}</label>{hint}</div>
    return <label className="checkbox-line field full">{box}{f.label}</label>
  }
  if (f.readonly) {
    return <div className="field full"><label htmlFor={id}>{f.label}</label><input id={id} value={f.readonly} readOnly aria-describedby={ids} />{hint}</div>
  }
  if (f.options) {
    return (
      <div className={f.short ? 'field short' : 'field'}>
        <label htmlFor={id}>{f.label}</label>
        <select id={id} data-setting={f.key} value={value ?? ''} disabled={f.disabled || undefined} aria-describedby={ids} aria-invalid={error ? 'true' : undefined} onChange={(e) => onChange(f.key, e.target.value)}>
          {optionTree(f.options)}
        </select>
        {hint}
      </div>
    )
  }
  return (
    <div className={['field', f.wide ? 'full' : f.short ? 'short' : ''].join(' ')}>
      <label htmlFor={id}>{f.label}</label>
      <input id={id} data-setting={f.key} value={value ?? ''} inputMode={f.numeric ? 'numeric' : undefined} autoComplete={f.type === 'password' ? 'new-password' : 'off'} spellCheck={false}
        type={f.type || undefined} placeholder={f.placeholder} disabled={f.disabled || undefined} aria-describedby={ids} aria-invalid={error ? 'true' : undefined} onChange={(e) => onChange(f.key, e.target.value)} />
      {hint}
      {error && <FieldError id={`err-${id}`} message={error} />}
    </div>
  )
}

/** Options [value, label] in order; a third element names an optgroup, consecutive options of one group share it. */
function optionTree(options) {
  const out = []
  for (const [o, l, g] of options) {
    const last = out[out.length - 1]
    if (g && last?.group === g) last.items.push([o, l])
    else out.push(g ? { group: g, items: [[o, l]] } : { option: [o, l] })
  }
  return out.map((x) => (x.group
    ? <optgroup key={`g-${x.group}`} label={x.group}>{x.items.map(([o, l]) => <option key={o} value={o}>{l}</option>)}</optgroup>
    : <option key={x.option[0]} value={x.option[0]}>{x.option[1]}</option>))
}

/** One section that fails to render leaves the others on the page. */
class SectionBoundary extends Component {
  constructor(props) { super(props); this.state = { failed: false } }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

/**
 * The frame of a section (settingsSection()): its heading, the refusal of its last save, then its
 * body. `aside` sits at the right of the heading (a state of the section).
 */
export function SettingsFrame({ id, label, desc, error, aside, children }) {
  const { t } = useTranslation()
  return (
    <section className="panel settings-section" id={`set-sec-${id}`} aria-labelledby={`set-title-${id}`}>
      <header className="panel-heading">
        <div>
          <h2 id={`set-title-${id}`} tabIndex={-1}>{label}</h2>
          {desc && <p>{desc}</p>}
          {error && <p className="field-error" role="alert"><Icon name="warning" /><span>{error}</span></p>}
        </div>
        {aside}
      </header>
      <div className="settings-body">
        <SectionBoundary fallback={<p className="field-error" role="alert"><Icon name="warning" /><span>{t('sectioned.sectionFailed')}</span></p>}>
          {children}
        </SectionBoundary>
      </div>
    </section>
  )
}

/**
 * A group of fields: `fieldset.settings-group`, its legend, the two (four) column grid; `grid={false}`
 * for blocks stacked one under the other. `hint` says what the group does, under its legend (absent from the mockup).
 */
export function SettingsGroup({ legend, hint, grid = true, children, ...rest }) {
  return (
    <fieldset className="settings-group" {...rest}>
      <legend>{legend}</legend>
      {hint && <p className="group-hint">{hint}</p>}
      <div className={grid ? 'settings-grid' : 'settings-stack'}>{children}</div>
    </fieldset>
  )
}

/**
 * A section's test (`.settings-test`): the button, then its result in the tone of the outcome, or
 * the hint at rest. result: { ok, text } | null. A field the test needs (`children`) precedes it.
 * `write={false}` for a check that only reads (the write guard lets it run).
 */
export function SettingsTest({ id, label, icon = 'send', onTest, busy = false, result, hint, buttonRef, write = true, children }) {
  return (
    <div className="settings-test">
      {children}
      <button type="button" className="btn" id={`test-${id}`} data-settings-test={id} data-write={write ? '' : undefined} ref={buttonRef} disabled={busy || undefined} onClick={onTest}>
        <Icon name={icon} />{label}
      </button>
      {result ? (
        <p className={`test-result ${result.ok ? 'good' : 'bad'}`} id={`test-result-${id}`} role="status"><Icon name={result.ok ? 'check' : 'warning'} /><span>{result.text}</span></p>
      ) : (
        <p className="test-result muted" id={`test-result-${id}`}><Icon name="help" /><span>{hint}</span></p>
      )}
    </div>
  )
}

/**
 * A section from data: its groups of fields and its test.
 * test: { label, onTest, result: { ok, text } | null, hint, busy }
 */
export function SettingsSection({ section: s, values, errors, onChange }) {
  return (
    <SettingsFrame id={s.id} label={s.label} desc={s.desc} error={s.error}>
      {s.groups.map((g) => (
        <SettingsGroup key={g.legend} legend={g.legend}>
          {g.fields.map((f) => (
            <SettingsField key={f.key} field={f} value={values[f.key]} error={errors[f.key]} onChange={onChange} />
          ))}
        </SettingsGroup>
      ))}
      {s.children}
      {s.test && <SettingsTest id={s.id} label={s.test.label} onTest={s.test.onTest} busy={s.test.busy} result={s.test.result} hint={s.test.hint} />}
    </SettingsFrame>
  )
}

const TOC_MARGIN = 8
const attrValue = (id) => String(id).replace(/["\\]/g, '\\$&')
const reducedMotion = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

const plainClick = (e) => e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey

/**
 * The table of contents: a link per section, marked « À corriger » or « Modifié »; `current` is the
 * shown one. `hrefFor` gives a link that opens the section in a new tab (the mockup's anchor otherwise).
 */
export function SettingsToc({ sections, flags = {}, current, label, onJump, hrefFor }) {
  const { t } = useTranslation()
  const ref = useRef(null)
  // Sticky at the top of the scroll area, never taller than what it shows: its last entries stay reachable
  useEffect(() => {
    const toc = ref.current
    const view = toc?.closest('.scroll-view')
    if (!view) return undefined
    const fit = () => {
      const pad = parseFloat(getComputedStyle(view).paddingBottom) || 0
      toc.style.maxHeight = view.clientHeight ? `${view.clientHeight - pad}px` : ''
    }
    fit()
    window.addEventListener('resize', fit)
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(fit)
    observer?.observe(view)
    return () => { window.removeEventListener('resize', fit); observer?.disconnect() }
  }, [])
  // The entry shown stays in view inside the table of contents (its own scroll only, never the page's)
  const first = useRef(true)
  useEffect(() => {
    const toc = ref.current
    const link = current && toc?.querySelector(`[data-jump="${attrValue(current)}"]`)
    const instant = first.current
    first.current = false
    if (!link || !toc.clientHeight) return
    const top = link.offsetTop
    const bottom = top + link.offsetHeight
    const to = top < toc.scrollTop + TOC_MARGIN ? top - TOC_MARGIN
      : bottom > toc.scrollTop + toc.clientHeight - TOC_MARGIN ? bottom - toc.clientHeight + TOC_MARGIN : null
    if (to !== null) toc.scrollTo?.({ top: Math.max(0, to), behavior: instant || reducedMotion() ? 'auto' : 'smooth' })
  }, [current, sections.length])
  return (
    <nav className="settings-toc" id="settings-toc" aria-label={label} ref={ref}>
      <ul>
        {sections.map((s) => (
          <li key={s.id}>
            <a href={hrefFor ? hrefFor(s.id) : `#set-sec-${s.id}`} data-jump={s.id} aria-current={current === s.id ? 'true' : undefined}
              onClick={(e) => {
                if (!plainClick(e)) return
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

/** The table of contents of a phone: `.field.settings-jump`, a select that jumps to the section. */
export function SettingsJump({ sections, current, onJump }) {
  const { t } = useTranslation()
  return (
    <div className="field settings-jump">
      <label htmlFor="settings-jump">{t('sectioned.jumpLabel')}</label>
      <select id="settings-jump" value={current || sections[0]?.id || ''} onChange={(e) => { jumpTo(e.target.value); onJump?.(e.target.value) }}>
        {sections.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
      </select>
    </div>
  )
}

/**
 * The save bar (settingsState() and its buttons), then the polite announcement. Pending fields
 * are named by `pending` (labels), else counted (`count`, `sections`); `failed` names the sections
 * whose save the server refused. `submit` makes Enregistrer the submit of an enclosing form.
 */
export function SettingsSaveBar({ dirty, pending = [], count = 0, sections = [], failed = [], lastSaved, saving = false, disabled = false,
  onReset, onSave, submit = false, stateRef, announce = '' }) {
  const { t } = useTranslation()
  const state = failed.length ? (
    <><Icon name="warning" /><span><strong>{t('sectioned.saveFailedTitle')}</strong>{t('sectioned.saveFailedIn', { sections: failed.join(', ') })}</span></>
  ) : dirty ? (
    <><Icon name="warning" /><span><strong>{t('sectioned.pendingTitle')}</strong>{pending.length
      ? t('sectioned.pendingFields', { fields: pending.join(', ') })
      : t('sectioned.pendingCount', { count, sections: sections.join(', ') })}</span></>
  ) : (
    <><Icon name="check" /><span>{t('sectioned.nothingPending')}{lastSaved && <>{' '}{lastSaved.by
      ? t('sectioned.lastSavedBy', { date: lastSaved.at, user: lastSaved.by }) : t('sectioned.lastSaved', { date: lastSaved.at })}</>}</span></>
  )
  return (
    <>
      <div className={dirty ? 'settings-savebar dirty' : 'settings-savebar'} id="settings-savebar">
        <p className="settings-state" id="settings-state" tabIndex={-1} ref={stateRef}>{state}</p>
        <button type="button" className="btn" id="settings-reset" data-action="settings-reset" disabled={!dirty || saving} onClick={onReset}>{t('sectioned.undo')}</button>
        <button type={submit ? 'submit' : 'button'} className="btn primary" id="settings-save" data-write="" disabled={!dirty || saving || disabled}
          onClick={submit ? undefined : onSave}>
          <Icon name="check" />{saving ? t('sectioned.saving') : t('common.save')}
        </button>
      </div>
      <p className="sr-only" id="settings-announce" role="status" aria-live="polite">{announce}</p>
    </>
  )
}

/** The history of changes under the form: `section.panel.settings-history`, its records in `.panel-content`. */
export function SettingsHistory({ title, text, children }) {
  return (
    <section className="panel settings-history" aria-labelledby="set-history-title">
      <header className="panel-heading"><div><h2 id="set-history-title">{title}</h2>{text && <p>{text}</p>}</div></header>
      <div className="panel-content">{children}</div>
    </section>
  )
}

/**
 * The layout: `.scroll-view > .settings-layout`, the table of contents, then the main column with
 * the form (its jump select, sections and save bar as `children`) and the history under it.
 * onSubmit: a `<form>` (its fields only); without it a `div.settings-form` that hears its keys.
 */
export function SettingsLayout({ toc, history, onSubmit, onKeyDown, children }) {
  return (
    <div className="scroll-view" id="view-scroll">
      <div className="settings-layout">
        {toc}
        <div className="settings-main">
          {onSubmit ? (
            <form className="settings-form" id="settings-form" noValidate onSubmit={(e) => { e.preventDefault(); onSubmit() }}>{children}</form>
          ) : (
            <div className="settings-form" id="settings-form" onKeyDown={onKeyDown}>{children}</div>
          )}
          {history}
        </div>
      </div>
    </div>
  )
}

/**
 * The whole form from data (the mockup's settingsFields).
 * @param {object} p
 * @param {Array} p.sections  { id, label, icon, desc, groups: [{ legend, fields }], test?, error?, children?, extraKeys? }
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
  const labelOf = Object.fromEntries([...sections.flatMap((s) => s.groups.flatMap((g) => g.fields)).map((f) => [f.key, f.label]), ...sections.flatMap((s) => s.extraKeys || [])])
  const flags = Object.fromEntries(sections.map((s) => {
    const keys = keysOf(s)
    return [s.id, keys.some((k) => errors[k]) || s.error ? 'error' : keys.some((k) => changed.includes(k)) ? 'modified' : '']
  }))
  return (
    <SettingsLayout
      toc={<SettingsToc sections={sections} flags={flags} current={current} label={tocLabel} onJump={onJump} />}
      history={history && <SettingsHistory title={history.title} text={history.text}>{history.children}</SettingsHistory>}
      onSubmit={() => onSave?.()}
    >
      <SettingsJump sections={sections} current={current} onJump={onJump} />
      {sections.map((s) => <SettingsSection key={s.id} section={s} values={values} errors={errors} onChange={onChange} />)}
      <SettingsSaveBar dirty={changed.length > 0} pending={changed.map((k) => labelOf[k] || k)} failed={failed} lastSaved={lastSaved}
        saving={saving} onReset={onReset} submit stateRef={stateRef} announce={announce} />
    </SettingsLayout>
  )
}

export default SettingsView
