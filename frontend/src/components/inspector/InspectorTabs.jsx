/**
 * Tab strips of the inspector: the open objects (closable, scrolled to the
 * active one, with a list of all of them when they overflow) and the sections
 * of the active object. Both follow the WAI-ARIA tabs pattern.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, CaretDown } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'
import { INSPECTOR_TYPES } from './config'

const TAB = 'inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium whitespace-nowrap border-b-2 transition-colors'
const ON = 'border-accent-primary text-text-primary'
const OFF = 'border-transparent text-text-secondary hover:text-text-primary'

// Arrow/Home/End move between the tabs of a list, activating the target
function arrowNav(e, count, current, select) {
  const to = { ArrowRight: (current + 1) % count, ArrowLeft: (current - 1 + count) % count, Home: 0, End: count - 1 }[e.key]
  if (to === undefined) return
  e.preventDefault()
  select(to)
}

export function tabId(key) { return `inspector-tab-${key.replace(/[^a-z0-9_-]/gi, '_')}` }
export function panelId(key) { return `inspector-panel-${key.replace(/[^a-z0-9_-]/gi, '_')}` }

export function ObjectTabs({ opened, activeKey, titles, onSelect, onClose }) {
  const { t } = useTranslation()
  const strip = useRef(null)
  const [menu, setMenu] = useState(false)

  useEffect(() => {
    strip.current?.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  }, [activeKey, opened.length])

  const label = (o) => titles[o.key] || `${t(`inspector.types.${o.type}`)} #${o.entityId}`
  const idx = opened.findIndex((o) => o.key === activeKey)
  const select = (i) => {
    onSelect(opened[i].key)
    requestAnimationFrame(() => strip.current?.querySelectorAll('[role="tab"]')[i]?.focus())
  }

  return (
    <div className="flex items-stretch min-w-0 flex-1 relative">
      <div ref={strip} role="tablist" aria-label={t('inspector.objectsLabel')}
        className="flex items-stretch min-w-0 overflow-x-auto" data-testid="inspector-object-tabs">
        {opened.map((o) => {
          const Icon = INSPECTOR_TYPES[o.type]?.icon
          const active = o.key === activeKey
          return (
            <div key={o.key} role="presentation" className={cn('flex items-center border-b-2 shrink-0', active ? 'border-accent-primary' : 'border-transparent')}>
              <button type="button" role="tab" id={tabId(o.key)} aria-selected={active} aria-controls={panelId(o.key)}
                tabIndex={active ? 0 : -1} onClick={() => onSelect(o.key)}
                onKeyDown={(e) => arrowNav(e, opened.length, idx, select)}
                className={cn(TAB, 'border-b-0 pr-1 max-w-[16rem]', active ? ON : OFF)}>
                {Icon && <Icon size={14} weight="duotone" />}
                <span className="truncate">{label(o)}</span>
              </button>
              <button type="button" onClick={() => onClose(o.key)} aria-label={t('inspector.closeTab', { name: label(o) })}
                className="p-1 mr-1 rounded text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary">
                <X size={12} />
              </button>
            </div>
          )
        })}
      </div>
      {opened.length > 3 && (
        <div className="relative shrink-0">
          <button type="button" aria-haspopup="true" aria-expanded={menu} aria-label={t('inspector.more')}
            onClick={() => setMenu((v) => !v)}
            className="h-full px-1.5 text-text-tertiary hover:text-text-primary"><CaretDown size={12} /></button>
          {menu && (
            <ul className="absolute right-0 top-full z-10 min-w-[12rem] max-h-64 overflow-auto bg-bg-secondary border border-border rounded-lg shadow-lg p-1"
              onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); setMenu(false) } }}>
              {opened.map((o) => (
                <li key={o.key}>
                  <button type="button" onClick={() => { onSelect(o.key); setMenu(false) }}
                    className={cn('w-full text-left px-2 py-1 text-xs rounded hover:bg-bg-tertiary', o.key === activeKey ? 'text-accent-primary' : 'text-text-secondary')}>
                    {label(o)}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

export function SectionTabs({ objectKey, sections, current, onSelect }) {
  const { t } = useTranslation()
  const ref = useRef(null)
  const idx = sections.indexOf(current)
  const select = (i) => {
    onSelect(sections[i])
    requestAnimationFrame(() => ref.current?.querySelectorAll('[role="tab"]')[i]?.focus())
  }
  return (
    <div ref={ref} role="tablist" aria-label={t('inspector.sectionsLabel')} className="shrink-0 flex items-stretch border-b border-border-op50 px-1">
      {sections.map((s) => (
        <button key={s} type="button" role="tab" id={`${tabId(objectKey)}-${s}`} aria-selected={s === current}
          aria-controls={`${panelId(objectKey)}-section`} tabIndex={s === current ? 0 : -1}
          onClick={() => onSelect(s)} onKeyDown={(e) => arrowNav(e, sections.length, idx, select)}
          className={cn(TAB, s === current ? ON : OFF)}>
          {t(`inspector.sections.${s}`)}
        </button>
      ))}
    </div>
  )
}
