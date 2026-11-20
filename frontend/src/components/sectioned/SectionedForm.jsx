/**
 * Sectioned form template (Atelier settings page): table of contents, a select to jump on
 * a phone, one full-width frame per section, groups of fields, a sticky save bar.
 */
import { Component, Fragment, forwardRef, useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Warning, WarningCircle } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'
import { ListButton } from '../list/PageHead'
import './sectioned.css'

export const sectionDomId = (id) => `sf-sec-${id}`
export const sectionTitleId = (id) => `sf-title-${id}`

/** Scrolls to a section's frame and gives its title the focus, as the Atelier jump does. */
export function jumpToSection(id) {
  const frame = document.getElementById(sectionDomId(id))
  if (!frame) return
  frame.scrollIntoView?.({ block: 'start' })
  document.getElementById(sectionTitleId(id))?.focus({ preventScroll: true })
}

/** Layout: the table of contents beside the main column. */
export function FormLayout({ toc, children, className }) {
  return (
    <div className={cn('sf-layout', className)}>
      {toc}
      <div className="sf-main">{children}</div>
    </div>
  )
}

/** One entry of the table of contents with its mark: modified, or to correct. */
function TocEntry({ section, flag, current, hrefFor, onJump }) {
  const { t } = useTranslation()
  const Icon = section.icon
  return (
    <li>
      <a
        href={hrefFor ? hrefFor(section.id) : `#${sectionDomId(section.id)}`}
        aria-current={current ? 'true' : undefined}
        data-jump={section.id}
        onClick={(e) => {
          // A plain click jumps in place; a modified click keeps the browser's behaviour
          if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
          e.preventDefault()
          onJump(section.id)
        }}
      >
        {Icon && <Icon aria-hidden="true" />}
        <span>{section.label}</span>
        {flag === 'error' ? (
          <span className="sf-flag is-bad"><Warning aria-hidden="true" />{t('sectioned.flagError')}</span>
        ) : flag === 'modified' ? (
          <span className="sf-flag">{t('sectioned.flagModified')}</span>
        ) : null}
      </a>
    </li>
  )
}

/**
 * Table of contents, by groups when `groups` is given: [{ id, label, ids }].
 * `flags` maps a section id to 'modified' or 'error'; `current` marks the shown section.
 */
export function SectionToc({ label, sections, groups, flags = {}, current, hrefFor, onJump }) {
  const byId = new Map(sections.map((s) => [s.id, s]))
  const entry = (s) => (
    <TocEntry key={s.id} section={s} flag={flags[s.id]} current={current === s.id} hrefFor={hrefFor} onJump={onJump} />
  )
  if (!groups?.length) {
    return (
      <nav className="sf-toc" aria-label={label}>
        <ul>{sections.map(entry)}</ul>
      </nav>
    )
  }
  return (
    <nav className="sf-toc" aria-label={label}>
      {groups.map((g) => {
        const items = g.ids.map((id) => byId.get(id)).filter(Boolean)
        if (!items.length) return null
        return (
          <div className="sf-toc-group" key={g.id} role="group" aria-labelledby={`sf-group-${g.id}`}>
            <p className="sf-toc-group-title" id={`sf-group-${g.id}`}>{g.label}</p>
            <ul>{items.map(entry)}</ul>
          </div>
        )
      })}
    </nav>
  )
}

/** The table of contents of a phone: a select that jumps to the section. */
export function SectionJump({ label, sections, value, onJump }) {
  const id = useId()
  return (
    <div className="sf-jump">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value || sections[0]?.id || ''} onChange={(e) => onJump(e.target.value)}>
        {sections.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
      </select>
    </div>
  )
}

/** One section that fails to render leaves the others on the page. */
class SectionBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

function SectionFailed() {
  const { t } = useTranslation()
  return <p className="sf-section-error" role="alert"><WarningCircle aria-hidden="true" /><span>{t('sectioned.sectionFailed')}</span></p>
}

/** Frame of one section: heading and its sentence, an error when its save failed, the body. */
export const FormSection = forwardRef(function FormSection(
  { id, title, description, aside, error, children, className, bodyClassName }, ref,
) {
  return (
    <section
      ref={ref}
      className={cn('sf-section', error && 'is-error', className)}
      id={sectionDomId(id)}
      aria-labelledby={sectionTitleId(id)}
      data-section={id}
    >
      <header className="sf-heading">
        <div>
          <h2 id={sectionTitleId(id)} tabIndex={-1}>{title}</h2>
          {description && <p>{description}</p>}
          {error && (
            <p className="sf-section-error" role="alert">
              <WarningCircle aria-hidden="true" /><span>{error}</span>
            </p>
          )}
        </div>
        {aside && <div className="sf-heading-aside">{aside}</div>}
      </header>
      <div className={cn('sf-body', bodyClassName)}>
        <SectionBoundary fallback={<SectionFailed />}>{children}</SectionBoundary>
      </div>
    </section>
  )
})

/** Properties read in a frame (the mockup's `.props`): a term and its value per line; a falsy item is skipped. */
export function FormProps({ items, className }) {
  return (
    <dl className={cn('sf-props', className)}>
      {items.filter(Boolean).map(([term, value]) => (
        <Fragment key={term}><dt>{term}</dt><dd>{value}</dd></Fragment>
      ))}
    </dl>
  )
}

/** A group of fields inside a section, with its legend; same props as the former detail section. */
export function FormGroup({ title, description, subtitle, actions, badge, children, className }) {
  const id = useId()
  const hasHead = title || actions
  return (
    <section className={cn('sf-group', className)} aria-labelledby={title ? id : undefined}>
      {hasHead && (
        <div className="sf-group-head">
          <div>
            {title && <h3 className="sf-legend" id={id}>{title}{badge}</h3>}
            {(description || subtitle) && <p className="sf-group-desc">{description || subtitle}</p>}
          </div>
          {actions && <div className="sf-group-actions">{actions}</div>}
        </div>
      )}
      <div className="sf-group-body">{children}</div>
    </section>
  )
}

/**
 * Save bar: nothing pending (with the last save when known), or the fields pending, with
 * « Undo changes » and « Save ». `stateRef` takes the focus after a save or an undo.
 */
export const SaveBar = forwardRef(function SaveBar(
  { count, sectionLabels = [], fieldLabels = [], lastSaved, saving, failed = [], onReset, onSave, disabled }, stateRef,
) {
  const { t } = useTranslation()
  const dirty = count > 0
  const state = failed.length ? (
    <>
      <Warning aria-hidden="true" />
      <span>
        <strong>{t('sectioned.saveFailedTitle')}</strong>
        {t('sectioned.saveFailedIn', { sections: failed.join(', ') })}
      </span>
    </>
  ) : dirty ? (
    <>
      <Warning aria-hidden="true" />
      <span>
        <strong>{t('sectioned.pendingTitle')}</strong>
        {/* The changed fields by name when the page knows them, else a count per section */}
        {fieldLabels.length
          ? t('sectioned.pendingFields', { fields: fieldLabels.join(', ') })
          : t('sectioned.pendingCount', { count, sections: sectionLabels.join(', ') })}
      </span>
    </>
  ) : (
    <>
      <Check aria-hidden="true" />
      <span>
        {t('sectioned.nothingPending')}
        {lastSaved && <>{' '}{lastSaved.by
          ? t('sectioned.lastSavedBy', { date: lastSaved.at, user: lastSaved.by })
          : t('sectioned.lastSaved', { date: lastSaved.at })}</>}
      </span>
    </>
  )
  return (
    <div className={cn('sf-savebar', dirty && 'is-dirty', failed.length > 0 && 'is-error')} data-testid="sf-savebar">
      <p className="sf-state" ref={stateRef} tabIndex={-1}>{state}</p>
      <ListButton type="button" onClick={onReset} disabled={!dirty || saving}>
        {t('sectioned.undo')}
      </ListButton>
      <ListButton type="button" primary icon={Check} onClick={onSave} disabled={!dirty || saving || disabled}>
        {saving ? t('sectioned.saving') : t('common.save')}
      </ListButton>
    </div>
  )
})
