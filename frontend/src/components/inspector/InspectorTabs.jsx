/**
 * Tab strips of the inspector. The open objects: closable tabs that share the width down
 * to a minimum, the active one always shown, the others in a "+N" menu. The sections of
 * the active object. Both follow the WAI-ARIA tabs pattern.
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, CaretDown } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'
import { INSPECTOR_TYPES } from './config'

// Width kept for the "+N" button when some objects do not fit
const MORE_W = 52

// Arrow/Home/End move between the tabs of a list, activating the target
function arrowNav(e, count, current, select) {
  const to = { ArrowRight: (current + 1) % count, ArrowLeft: (current - 1 + count) % count, Home: 0, End: count - 1 }[e.key]
  if (to === undefined) return
  e.preventDefault()
  select(to)
}

export function tabId(key) { return `inspector-tab-${key.replace(/[^a-z0-9_-]/gi, '_')}` }
export function panelId(key) { return `inspector-panel-${key.replace(/[^a-z0-9_-]/gi, '_')}` }

/** The objects drawn as tabs and those left to the menu; the active one is always drawn. */
export function splitTabs(opened, activeKey, fit) {
  if (opened.length <= fit) return { shown: opened, hidden: [] }
  const room = Math.max(1, fit)
  let shown = opened.slice(0, room)
  const active = opened.find((o) => o.key === activeKey)
  if (active && !shown.includes(active)) shown = [...shown.slice(0, room - 1), active]
  return { shown, hidden: opened.filter((o) => !shown.includes(o)) }
}

export function ObjectTabs({ opened, activeKey, titles, onSelect, onClose, badge }) {
  const { t } = useTranslation()
  const strip = useRef(null)
  const more = useRef(null)
  const moreBtn = useRef(null)
  const [fit, setFit] = useState(Infinity)
  const [tight, setTight] = useState(false)
  const [width, setWidth] = useState(0)
  const [menu, setMenu] = useState(false)
  const count = opened.length

  // How many tabs of the minimum width fit; an unmeasured strip (no layout) keeps them all
  useLayoutEffect(() => {
    const el = strip.current
    if (!el) return undefined
    const measure = () => {
      const avail = el.clientWidth + (more.current?.offsetWidth || 0)
      setWidth(avail)
      if (!avail) { setFit(Infinity); return }
      const min = parseFloat(getComputedStyle(el).getPropertyValue('--insp-tab-min')) || 120
      setFit(count * min <= avail ? Infinity : Math.max(1, Math.floor((avail - MORE_W) / min)))
    }
    measure()
    if (typeof ResizeObserver !== 'function') return undefined
    const observer = new ResizeObserver(measure)
    observer.observe(el.parentElement)
    return () => observer.disconnect()
  }, [count])

  const { shown, hidden } = splitTabs(opened, activeKey, fit)
  const shownKeys = shown.map((o) => o.key).join()

  // Tabs wider than the strip share its width instead of pushing each other out
  useLayoutEffect(() => {
    const el = strip.current
    if (!el) return
    el.classList.remove('is-tight')
    const over = el.scrollWidth > el.clientWidth
    el.classList.toggle('is-tight', over)
    setTight(over)
  }, [shownKeys, titles, fit, width])

  useEffect(() => { if (!hidden.length) setMenu(false) }, [hidden.length])
  useEffect(() => {
    if (!menu) return undefined
    const away = (e) => { if (!more.current?.contains(e.target)) setMenu(false) }
    document.addEventListener('pointerdown', away)
    return () => document.removeEventListener('pointerdown', away)
  }, [menu])

  const label = (o) => titles[o.key] || `${t(`inspector.types.${o.type}`)} #${o.entityId}`
  const idx = shown.findIndex((o) => o.key === activeKey)
  const select = (i) => {
    onSelect(shown[i].key)
    requestAnimationFrame(() => strip.current?.querySelectorAll('[role="tab"]')[i]?.focus())
  }
  const openMenu = (edge) => {
    setMenu(true)
    requestAnimationFrame(() => {
      const items = more.current?.querySelectorAll('.insp-menu-open') || []
      items[edge === 'last' ? items.length - 1 : 0]?.focus()
    })
  }
  const closeMenu = (refocus) => {
    setMenu(false)
    if (refocus) moreBtn.current?.focus()
  }
  const onMenuKey = (e) => {
    if (e.key === 'Escape' || e.key === 'Tab') {
      e.preventDefault()
      e.stopPropagation()
      closeMenu(true)
      return
    }
    const column = e.target.classList.contains('insp-x') ? '.insp-x' : '.insp-menu-open'
    const items = [...e.currentTarget.querySelectorAll(column)]
    const i = items.indexOf(e.target)
    const to = { ArrowDown: (i + 1) % items.length, ArrowUp: (i - 1 + items.length) % items.length, Home: 0, End: items.length - 1 }[e.key]
    if (to !== undefined) {
      e.preventDefault()
      items[to]?.focus()
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      e.target.parentElement.querySelector(column === '.insp-x' ? '.insp-menu-open' : '.insp-x')?.focus()
    }
  }

  return (
    <>
      <div ref={strip} role="tablist" aria-label={t('inspector.objectsLabel')}
        className={cn('insp-tabs', tight && 'is-tight')} data-testid="inspector-object-tabs">
        {shown.map((o) => {
          const Icon = INSPECTOR_TYPES[o.type]?.icon
          const active = o.key === activeKey
          return (
            <div key={o.key} role="presentation" className={cn('insp-tab', active && 'is-active')}>
              <button type="button" role="tab" id={tabId(o.key)} aria-selected={active} aria-controls={panelId(o.key)}
                tabIndex={active ? 0 : -1} title={label(o)} onClick={() => onSelect(o.key)}
                onKeyDown={(e) => {
                  // Delete closes the focused tab, as its own button does
                  if (e.key === 'Delete') { e.preventDefault(); onClose(o.key); return }
                  arrowNav(e, shown.length, idx, select)
                }}>
                {Icon && <Icon aria-hidden="true" />}
                <span className="insp-tab-name">{label(o)}</span>
              </button>
              <button type="button" className="insp-x" onClick={() => onClose(o.key)} aria-label={t('inspector.closeTab', { name: label(o) })}>
                <X aria-hidden="true" />
              </button>
            </div>
          )
        })}
      </div>
      {hidden.length > 0 && (
        <div className="insp-more" ref={more}>
          <button type="button" ref={moreBtn} className="insp-more-btn" data-testid="inspector-more"
            aria-haspopup="menu" aria-expanded={menu} title={t('inspector.moreCount', { count: hidden.length })}
            onClick={() => (menu ? closeMenu(false) : openMenu('first'))}
            onKeyDown={(e) => {
              if (menu || (e.key !== 'ArrowDown' && e.key !== 'ArrowUp')) return
              e.preventDefault()
              openMenu(e.key === 'ArrowUp' ? 'last' : 'first')
            }}>
            <span aria-hidden="true">+{hidden.length}</span>
            <span className="sr-only">{t('inspector.moreCount', { count: hidden.length })}</span>
            <CaretDown aria-hidden="true" />
          </button>
          {menu && (
            <ul className="insp-menu" role="menu" aria-label={t('inspector.notShown')} onKeyDown={onMenuKey}>
              {hidden.map((o) => {
                const Icon = INSPECTOR_TYPES[o.type]?.icon
                return (
                  <li key={o.key} role="none">
                    <button type="button" role="menuitem" tabIndex={-1} className="insp-menu-open" title={label(o)}
                      onClick={() => { onSelect(o.key); setMenu(false) }}>
                      {Icon && <Icon aria-hidden="true" />}
                      <span className="insp-menu-name">{label(o)}</span>
                      {badge?.(o)}
                    </button>
                    <button type="button" role="menuitem" tabIndex={-1} className="insp-x"
                      aria-label={t('inspector.closeTab', { name: label(o) })}
                      onClick={(e) => {
                        // The next row takes the focus, or the button once the menu is empty
                        const rows = [...e.currentTarget.closest('ul').querySelectorAll('.insp-x')]
                        const at = rows.indexOf(e.currentTarget)
                        onClose(o.key)
                        requestAnimationFrame(() => {
                          const left = more.current?.querySelectorAll('.insp-x') || []
                          if (left.length) left[Math.min(at, left.length - 1)].focus()
                          else strip.current?.querySelector('[aria-selected="true"]')?.focus()
                        })
                      }}>
                      <X aria-hidden="true" />
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </>
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
    <div ref={ref} role="tablist" aria-label={t('inspector.sectionsLabel')} className="insp-sections">
      {sections.map((s) => (
        <button key={s} type="button" role="tab" id={`${tabId(objectKey)}-${s}`} aria-selected={s === current}
          aria-controls={`${panelId(objectKey)}-section`} tabIndex={s === current ? 0 : -1}
          onClick={() => onSelect(s)} onKeyDown={(e) => arrowNav(e, sections.length, idx, select)}>
          {t(`inspector.sections.${s}`)}
        </button>
      ))}
    </div>
  )
}
