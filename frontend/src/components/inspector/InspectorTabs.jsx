/**
 * Tab strips of the inspector: the open objects (closable, the active one always
 * shown, the others beyond the width in a « +N » menu) and the sections of the
 * active object. Both follow the WAI-ARIA tabs pattern.
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, CaretDown } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'
import { INSPECTOR_TYPES } from './config'
import { splitTabs, tabsThatFit } from './tabFit'
import './inspector.css'

// Arrow/Home/End move between the tabs of a list, activating the target
function arrowNav(e, count, current, select) {
  const to = { ArrowRight: (current + 1) % count, ArrowLeft: (current - 1 + count) % count, Home: 0, End: count - 1 }[e.key]
  if (to === undefined) return
  e.preventDefault()
  select(to)
}

export function tabId(key) { return `inspector-tab-${key.replace(/[^a-z0-9_-]/gi, '_')}` }
export function panelId(key) { return `inspector-panel-${key.replace(/[^a-z0-9_-]/gi, '_')}` }

export function ObjectTabs({ opened, activeKey, titles, onSelect, onClose, tabMin = 120 }) {
  const { t } = useTranslation()
  const zone = useRef(null)
  const strip = useRef(null)
  const moreBtn = useRef(null)
  const menuRef = useRef(null)
  const [avail, setAvail] = useState(0)
  const [menu, setMenu] = useState(false)

  // The width the strip and its « +N » button share, followed as the dock resizes
  useLayoutEffect(() => {
    const el = zone.current
    if (!el) return undefined
    const measure = () => setAvail(el.clientWidth)
    measure()
    if (typeof ResizeObserver !== 'function') return undefined
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const keys = opened.map((o) => o.key)
  const { shown, hidden } = splitTabs(keys, activeKey, tabsThatFit(avail, tabMin, keys.length))
  const byKey = Object.fromEntries(opened.map((o) => [o.key, o]))
  const label = (o) => titles[o.key] || `${t(`inspector.types.${o.type}`)} #${o.entityId}`
  const idx = shown.indexOf(activeKey)

  useEffect(() => { if (!hidden.length) setMenu(false) }, [hidden.length])

  const focusTab = (key) => requestAnimationFrame(() => document.getElementById(tabId(key))?.focus())
  const select = (i) => {
    onSelect(shown[i])
    focusTab(shown[i])
  }
  // Delete closes the focused tab from the keyboard; the focus stays in the strip
  const onTabKey = (e, key) => {
    if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault()
      onClose(key)
      return
    }
    arrowNav(e, shown.length, idx, select)
  }

  const closeMenu = (refocus) => {
    setMenu(false)
    if (refocus) requestAnimationFrame(() => moreBtn.current?.focus())
  }
  const menuItems = () => [...(menuRef.current?.querySelectorAll('[role="menuitem"]') || [])]
  const openMenu = (focus = 'first') => {
    setMenu(true)
    requestAnimationFrame(() => {
      const items = menuItems().filter((el) => el.dataset.open)
      ;(focus === 'last' ? items.at(-1) : items[0])?.focus()
    })
  }
  const onMenuKey = (e) => {
    const items = menuItems()
    const at = items.indexOf(document.activeElement)
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeMenu(true) }
    else if (e.key === 'Tab') closeMenu(false)
    else if (e.key === 'ArrowDown') { e.preventDefault(); items[(at + 1) % items.length]?.focus() }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items[(at - 1 + items.length) % items.length]?.focus() }
    else if (e.key === 'ArrowRight' && at >= 0) { e.preventDefault(); items[at + 1]?.focus() }
    else if (e.key === 'ArrowLeft' && at >= 0) { e.preventDefault(); items[at - 1]?.focus() }
  }

  useEffect(() => {
    if (!menu) return undefined
    const away = (e) => {
      if (!menuRef.current?.contains(e.target) && !moreBtn.current?.contains(e.target)) setMenu(false)
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [menu])

  return (
    <div ref={zone} className="ins-tabs-zone">
      <div ref={strip} role="tablist" aria-label={t('inspector.objectsLabel')} className="ins-open-tabs"
        data-testid="inspector-object-tabs" style={{ '--tab-min': `${tabMin}px` }}>
        {shown.map((key) => {
          const o = byKey[key]
          const Icon = INSPECTOR_TYPES[o.type]?.icon
          const active = key === activeKey
          return (
            <div key={key} role="presentation" className={cn('ins-open-tab', active && 'is-active')}>
              <button type="button" role="tab" id={tabId(key)} aria-selected={active} aria-controls={panelId(key)}
                tabIndex={active ? 0 : -1} title={label(o)} onClick={() => onSelect(key)}
                onKeyDown={(e) => onTabKey(e, key)} className="ins-open-tab-label">
                {Icon && <Icon size={13} aria-hidden="true" />}
                <span className="ins-tab-name">{label(o)}</span>
              </button>
              <button type="button" onClick={() => onClose(key)} aria-label={t('inspector.closeTab', { name: label(o) })}
                className="ins-icon-btn is-tab-close">
                <X size={12} aria-hidden="true" />
              </button>
            </div>
          )
        })}
      </div>
      {hidden.length > 0 && (
        <div className="ins-tabs-more">
          <button ref={moreBtn} type="button" className="ins-tabs-more-btn" data-testid="inspector-tabs-more"
            aria-haspopup="menu" aria-expanded={menu} aria-controls="inspector-tabs-menu"
            title={t('inspector.moreOpen', { count: hidden.length })}
            onClick={() => (menu ? closeMenu(false) : openMenu())}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') { e.preventDefault(); openMenu('first') }
              else if (e.key === 'ArrowUp') { e.preventDefault(); openMenu('last') }
            }}>
            +{hidden.length}
            <span className="sr-only"> {t('inspector.moreOpen', { count: hidden.length })}</span>
            <CaretDown size={12} aria-hidden="true" />
          </button>
          {menu && (
            <ul ref={menuRef} id="inspector-tabs-menu" role="menu" aria-label={t('inspector.hiddenObjects')}
              className="ins-pop ins-tabs-menu" onKeyDown={onMenuKey}>
              {hidden.map((key) => {
                const o = byKey[key]
                const Icon = INSPECTOR_TYPES[o.type]?.icon
                return (
                  <li key={key} role="none">
                    <button type="button" role="menuitem" tabIndex={-1} data-open="true" title={label(o)}
                      className="ins-tabs-menu-open" onClick={() => { onSelect(key); setMenu(false); focusTab(key) }}>
                      {Icon && <Icon size={13} aria-hidden="true" />}
                      <span className="ins-pop-label">{label(o)}</span>
                    </button>
                    <button type="button" role="menuitem" tabIndex={-1} className="ins-icon-btn"
                      aria-label={t('inspector.closeTab', { name: label(o) })} onClick={() => onClose(key)}>
                      <X size={12} aria-hidden="true" />
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

export function SectionTabs({ objectKey, sections, current, onSelect, labelOf }) {
  const { t } = useTranslation()
  const ref = useRef(null)
  const idx = sections.indexOf(current)
  const select = (i) => {
    onSelect(sections[i])
    requestAnimationFrame(() => ref.current?.querySelectorAll('[role="tab"]')[i]?.focus())
  }
  return (
    <div ref={ref} role="tablist" aria-label={t('inspector.sectionsLabel')} className="ins-detail-tabs">
      {sections.map((s) => (
        <button key={s} type="button" role="tab" id={`${tabId(objectKey)}-${s}`} aria-selected={s === current}
          aria-controls={`${panelId(objectKey)}-section`} tabIndex={s === current ? 0 : -1}
          onClick={() => onSelect(s)} onKeyDown={(e) => arrowNav(e, sections.length, idx, select)}>
          {labelOf ? labelOf(s) : t(`inspector.sections.${s}`)}
        </button>
      ))}
    </div>
  )
}
