/**
 * The mockup's inspector dock: dockFrame() (the frame under the page, its resize grip, the open
 * tabs with their « +N » menu, the size, fold and close tools) and dockBody() (the heading with
 * the object's actions, its section tabs and the panel). On a phone the dock covers the screen as
 * a modal dialog: its close button takes the focus, Tab stays in it and the page behind is inert.
 * Escape closes it from anywhere on the page, unless a dialog or a menu answers Escape itself; on
 * close the focus returns to the row button of the object, else to the control that opened it.
 * Its position, size and fold are the user's one dock preference, the same on every page.
 */
import { useContext, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMobile } from '../../contexts/MobileContext'
import { splitTabs, tabsThatFit } from '../inspector/tabFit'
import { useToolbarMenu } from '../list/useToolbarMenu'
import { Icon } from './Icon'
import { heightMax, heightMin } from './helpers'
import { DOCK_RIGHT_MIN, DockSideContext, useDockPreference } from './dockSide'
import { useDockMounted } from './openDocks'

const STEP = 20
const WIDTH = [360, 720]
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))
const OWN_ESCAPE = '[role="dialog"][aria-modal="true"]:not(.inspector), dialog[open], [role="alertdialog"], [role="menu"]:not([hidden]), [role="listbox"], [data-radix-popper-content-wrapper]'
const ownLayerOpen = () => [...document.querySelectorAll(OWN_ESCAPE)].some((el) => !el.closest('[hidden]'))
const visible = (el) => el && el.isConnected && el.getClientRects().length > 0
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]'
// What the full-screen dock covers on a phone, inert while it is open (the mockup's `cover`)
const BEHIND = '.skip, .masthead, .shell-banners, .statusbar, .page-content'
const MODAL = 'dialog[open], [role="dialog"][aria-modal="true"], [role="alertdialog"]'

/** The section tabs and the panel of the active object. */
/** idPrefix: set where the body is shown twice (a detached window beside the dock), so its ids stay unique. */
export function DockBody({ icon, title, badge, actions, sections, section, onSection, sectionsLabel, busy = false, idPrefix = '', children }) {
  const ref = useRef(null)
  const ids = sections.map(([v]) => v)
  const onKey = (e) => {
    const n = ids.length
    const i = ids.indexOf(section)
    const to = { ArrowRight: (i + 1) % n, ArrowLeft: (i - 1 + n) % n, Home: 0, End: n - 1 }[e.key]
    if (to === undefined) return
    e.preventDefault()
    onSection(ids[to])
    requestAnimationFrame(() => ref.current?.querySelector(`#${idPrefix}tab-${ids[to]}`)?.focus())
  }
  return (
    <div className="dock-body">
      <header className="dock-heading">
        <div className="detail-title"><Icon name={icon} /><h2>{title}</h2>{badge}</div>
        <div className="actions">{actions}</div>
      </header>
      <div ref={ref} className="detail-tabs" role="tablist" aria-label={sectionsLabel}>
        {sections.map(([value, label]) => (
          <button key={value} type="button" role="tab" id={`${idPrefix}tab-${value}`} data-detail-tab={value} aria-selected={section === value}
            aria-controls={`${idPrefix}detail-panel`} tabIndex={section === value ? 0 : -1} onClick={() => onSection(value)} onKeyDown={onKey}>
            {label}
          </button>
        ))}
      </div>
      <div className="detail-panel" id={`${idPrefix}detail-panel`} role="tabpanel" aria-labelledby={`${idPrefix}tab-${section}`} tabIndex={0} aria-busy={busy || undefined}>
        {children}
      </div>
    </div>
  )
}

/** The open tabs: closable, the active one always shown, those beyond the width in the « +N » menu. */
function OpenTabs({ tabs, activeKey, onSelect, onClose, label, moreTitle, hiddenLabel }) {
  const { t } = useTranslation()
  const strip = useRef(null)
  const more = useRef(null)
  const [avail, setAvail] = useState(0)
  const [min, setMin] = useState(120)
  const [menu, setMenu] = useState(false)
  const { buttonRef, menuRef, onButtonKeyDown } = useToolbarMenu(menu, setMenu)
  // The width the strip and its « +N » button share, followed as the dock resizes (the mockup's fitTabs)
  useLayoutEffect(() => {
    const el = strip.current
    if (!el) return undefined
    const measure = () => {
      setAvail(el.clientWidth + (more.current?.offsetWidth || 0))
      setMin(parseFloat(getComputedStyle(el).getPropertyValue('--tab-min')) || 120)
    }
    measure()
    if (typeof ResizeObserver !== 'function') return undefined
    const ro = new ResizeObserver(measure)
    ro.observe(el.parentElement)
    return () => ro.disconnect()
  }, [])
  const keys = tabs.map((x) => x.key)
  const { shown, hidden } = splitTabs(keys, activeKey, tabsThatFit(avail, min, keys.length))
  const byKey = Object.fromEntries(tabs.map((x) => [x.key, x]))
  useLayoutEffect(() => {
    const el = strip.current
    if (!el) return
    el.classList.remove('tight')
    el.classList.toggle('tight', el.scrollWidth > el.clientWidth)
  })
  useEffect(() => { if (!hidden.length) setMenu(false) }, [hidden.length])
  // A click or the focus elsewhere closes the menu, as the mockup's focusout does
  useEffect(() => {
    if (!menu) return undefined
    const inside = (el) => menuRef.current?.contains(el) || buttonRef.current?.contains(el)
    const away = (e) => { if (!inside(e.target)) setMenu(false) }
    const out = (e) => { if (e.relatedTarget && !inside(e.relatedTarget)) setMenu(false) }
    document.addEventListener('pointerdown', away)
    document.addEventListener('focusout', out)
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('focusout', out) }
  }, [menu, menuRef, buttonRef])
  const onKey = (e, key) => {
    if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); onClose(key); return }
    const i = shown.indexOf(key)
    const to = { ArrowRight: (i + 1) % shown.length, ArrowLeft: (i - 1 + shown.length) % shown.length }[e.key]
    if (to === undefined) return
    e.preventDefault()
    onSelect(shown[to])
    requestAnimationFrame(() => strip.current?.querySelector(`[data-active="${CSS.escape(String(shown[to]))}"]`)?.focus())
  }
  return (
    <>
      <div ref={strip} className="open-tabs" aria-label={label}>
        {shown.map((key) => {
          const tab = byKey[key]
          const active = key === activeKey
          return (
            <div key={key} className={active ? 'open-tab active' : 'open-tab'}>
              <button type="button" data-active={key} aria-pressed={active} title={tab.title} onClick={() => onSelect(key)} onKeyDown={(e) => onKey(e, key)}>
                <Icon name={tab.icon} /><span className="tab-name">{tab.title}</span>
              </button>
              <button type="button" className="icon-btn" data-close-tab={key} aria-label={t('inspector.closeTab', { name: tab.title })} onClick={() => onClose(key)}>
                <Icon name="close" />
              </button>
            </div>
          )
        })}
      </div>
      {hidden.length > 0 && (
        <div ref={more} className="tabs-more" id="tabs-more-wrap">
          <button ref={buttonRef} type="button" className="tabs-more-btn" id="tabs-more-btn" aria-haspopup="menu" aria-expanded={menu}
            aria-controls="tabs-menu" title={moreTitle(hidden.length)} onClick={() => setMenu(!menu)} onKeyDown={onButtonKeyDown}>
            +{hidden.length}<span className="sr-only"> {hiddenLabel(hidden.length)}</span><Icon name="down" />
          </button>
          <ul ref={menuRef} className="pop-menu tabs-menu" id="tabs-menu" role="menu" aria-label={label} hidden={!menu}>
            {hidden.map((key) => {
              const tab = byKey[key]
              return (
                <li key={key} role="none">
                  <button type="button" role="menuitem" tabIndex={-1} className="tabs-menu-open" data-active={key} title={tab.title}
                    onClick={() => { onSelect(key); setMenu(false) }}>
                    <Icon name={tab.icon} /><span className="pop-label">{tab.title}</span>{tab.badge}
                  </button>
                  <button type="button" role="menuitem" tabIndex={-1} className="icon-btn tabs-menu-close" data-close-tab={key}
                    aria-label={t('inspector.closeTab', { name: tab.title })} onClick={() => onClose(key)}>
                    <Icon name="close" />
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </>
  )
}

/**
 * @param {object} p
 * @param {string} p.label  the dock's name (« Inspecteur de certificat », « Détail : Modèles »)
 * @param {string} p.tabsLabel  the name of the open tabs
 * @param {Array<{key, title, icon, badge?}>} p.tabs  with `onCloseTab` they are closable tabs; else the one open object's label
 * @param {string} p.activeKey
 * @param {() => void} p.onClose
 * @param {() => void} [p.onDetach]  opens the active object in a detached window (a tool of the bar)
 * @param {import('react').ReactNode} p.children  a DockBody
 */
export function Dock({ label, tabsLabel, tabs, activeKey, onSelectTab, onCloseTab, onClose, onDetach, children }) {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  useDockMounted()
  const setZoneRight = useContext(DockSideContext)
  const ref = useRef(null)
  const pref = useDockPreference()
  const { height: stored, width: storedW, position: side, collapsed, setCollapsed } = pref
  const setStored = (v) => pref.setGeometry({ height: v })
  const setStoredW = (v) => pref.setGeometry({ width: v })
  const setSide = (v) => pref.setGeometry({ position: v })
  const [viewW, setViewW] = useState(() => window.innerWidth)
  const [drag, setDrag] = useState(null)
  // The right needs room for the list beside it: under the threshold the dock goes back to the bottom
  const right = side === 'right' && viewW >= DOCK_RIGHT_MIN && !isMobile
  const height = clamp(drag ?? Number(stored) ?? 278, heightMin(), heightMax())
  const width = clamp(drag ?? Number(storedW) ?? 460, WIDTH[0], WIDTH[1])
  const folded = collapsed && !isMobile && !right
  const opener = useRef(typeof document !== 'undefined' ? document.activeElement : null)
  const active = useRef(activeKey)
  active.current = activeKey
  const close = useRef(onClose)
  close.current = onClose

  useEffect(() => {
    const onResize = () => setViewW(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  useEffect(() => {
    setZoneRight?.(right)
    return () => setZoneRight?.(false)
  }, [right, setZoneRight])

  // A module object opened unfolds the dock (the mockup's openItem()); Certificates unfold in openEntity
  useEffect(() => {
    if (!onCloseTab) setCollapsed(false)
  }, [activeKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // On a phone the dock is a dialog over the page: its close button takes the focus
  useEffect(() => {
    if (isMobile) ref.current?.querySelector('[data-action="close-dock"]')?.focus()
  }, [isMobile])

  // On a phone the page, the bars and the skip link are inert behind the dock, as the mockup's cover;
  // a part that holds a modal dialog opened over the dock is not (the dialog makes the rest inert)
  useEffect(() => {
    if (!isMobile) return undefined
    const dock = ref.current
    const covered = [...document.querySelectorAll(BEHIND)].filter((el) => !el.hasAttribute('inert') && !el.contains(dock))
    const sync = () => covered.forEach((el) => {
      const holds = el.querySelector(MODAL)
      if (holds && el.hasAttribute('inert')) el.removeAttribute('inert')
      else if (!holds && !el.hasAttribute('inert')) el.setAttribute('inert', '')
    })
    sync()
    const watch = new MutationObserver(sync)
    covered.forEach((el) => watch.observe(el, { subtree: true, childList: true, attributes: true, attributeFilter: ['open', 'aria-modal'] }))
    return () => {
      watch.disconnect()
      covered.forEach((el) => el.removeAttribute('inert'))
    }
  }, [isMobile])

  // On a phone Tab and Shift Tab go round the dock's controls; a dialog over it keeps its own
  useEffect(() => {
    if (!isMobile) return undefined
    const onKey = (e) => {
      const dock = ref.current
      const cur = document.activeElement
      if (e.key !== 'Tab' || e.defaultPrevented || !dock) return
      if (cur && !dock.contains(cur) && cur.closest?.('dialog, [role="dialog"], [role="alertdialog"]')) return
      const els = [...dock.querySelectorAll(FOCUSABLE)].filter((el) => el.tabIndex >= 0 && !el.closest('[hidden]') && visible(el))
      if (!els.length) return
      const inside = dock.contains(cur)
      const edge = e.shiftKey ? els[0] : els.at(-1)
      if (inside && cur !== edge) return
      e.preventDefault()
      ;(e.shiftKey ? els.at(-1) : els[0]).focus()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [isMobile])

  // The focus goes back to the row button of the object, else to the opener, once the dock is gone;
  // a mobile record carries the key too but takes no focus: its name button does
  useEffect(() => () => {
    const key = active.current
    const back = opener.current
    requestAnimationFrame(() => {
      const row = [...document.querySelectorAll(`[data-open="${CSS.escape(String(key))}"]`)].find((el) => visible(el) && !el.closest('.inspector') && el.matches(FOCUSABLE))
      const target = row || (visible(back) ? back : null)
      if (target) target.focus()
    })
  }, [])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Escape' || e.defaultPrevented || ownLayerOpen()) return
      e.preventDefault()
      close.current?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const setSize = (v) => {
    if (right) setStoredW(Math.round(clamp(v, WIDTH[0], WIDTH[1])))
    else setStored(Math.round(clamp(v, heightMin(), heightMax())))
    setCollapsed(false)
  }
  const size = right ? width : height
  const onGripKey = (e) => {
    const v = right
      ? { ArrowLeft: width + STEP, ArrowRight: width - STEP, Home: WIDTH[0], End: WIDTH[1] }[e.key]
      : { ArrowUp: height + STEP, ArrowDown: height - STEP, Home: heightMin(), End: heightMax() }[e.key]
    if (v === undefined) return
    e.preventDefault()
    setSize(v)
  }
  const onGripDown = (e) => {
    e.preventDefault()
    const start = right ? e.clientX : e.clientY
    const from = size
    let last = from
    e.currentTarget.setPointerCapture?.(e.pointerId)
    const move = (ev) => {
      last = right ? clamp(from + start - ev.clientX, WIDTH[0], WIDTH[1]) : clamp(from + start - ev.clientY, heightMin(), heightMax())
      setDrag(last)
    }
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); setDrag(null); setSize(last) }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  const grown = right ? width >= 600 : height >= 360

  return (
    <aside ref={ref} className={folded ? 'inspector collapsed' : 'inspector'} id="inspector" aria-label={label}
      {...(isMobile ? { role: 'dialog', 'aria-modal': 'true' } : {})} style={{ '--dock': `${height}px`, '--dock-w': `${width}px` }}>
      <div className="resize-grip" id="dock-resize" role="separator" tabIndex={0}
        aria-label={t(right ? 'inspector.resizeWidth' : 'inspector.resizeHeight')} aria-orientation={right ? 'vertical' : 'horizontal'}
        aria-valuemin={right ? WIDTH[0] : heightMin()} aria-valuemax={right ? WIDTH[1] : heightMax()} aria-valuenow={Math.round(size)}
        onKeyDown={onGripKey} onPointerDown={onGripDown} />
      <div className="dock-tabs">
        {onCloseTab ? (
          <OpenTabs tabs={tabs} activeKey={activeKey} onSelect={(k) => { onSelectTab?.(k); setCollapsed(false) }} onClose={onCloseTab} label={tabsLabel}
            moreTitle={(n) => t('inspector.moreOpen', { count: n })} hiddenLabel={(n) => t('inspector.hiddenObjectsCount', { count: n })} />
        ) : (
          <div className="open-tabs" aria-label={tabsLabel}>
            {tabs.map((tab) => (
              <div key={tab.key} className="open-tab active">
                <span className="open-tab-label"><Icon name={tab.icon} /><span className="tab-name">{tab.title}</span></span>
              </div>
            ))}
          </div>
        )}
        <div className="dock-tools">
          {viewW >= DOCK_RIGHT_MIN && (
            <button type="button" className="icon-btn dock-side-button" data-action="dock-side" aria-label={t(right ? 'inspector.dockBottom' : 'inspector.dockRight')}
              title={t(right ? 'inspector.dockBottom' : 'inspector.dockRight')} onClick={() => { setSide(right ? 'bottom' : 'right'); setCollapsed(false) }}>
              <Icon name={right ? 'dockBottom' : 'dockRight'} />
            </button>
          )}
          <button type="button" className="icon-btn size-button" data-action="dock-size" aria-label={t(grown ? 'inspector.shrink' : 'inspector.grow')}
            title={t(right ? 'inspector.changeWidth' : 'inspector.changeHeight')}
            onClick={() => setSize(right ? (grown ? 460 : 640) : (grown ? 278 : Math.min(420, heightMax())))}>
            <Icon name="expand" />
          </button>
          {!right && (
            <button type="button" className="icon-btn collapse-button" data-action="dock-collapse" aria-expanded={!folded}
              aria-label={t(folded ? 'inspector.expand' : 'inspector.collapse')} onClick={() => setCollapsed(!collapsed)}>
              <Icon name={folded ? 'up' : 'minimize'} />
            </button>
          )}
          {onDetach && !isMobile && (
            <button type="button" className="icon-btn" data-action="dock-detach" aria-label={t('inspector.detach')} title={t('inspector.detach')} onClick={onDetach}>
              <Icon name="layers" />
            </button>
          )}
          <button type="button" className="icon-btn" data-action="close-dock" aria-label={t('inspector.close')} onClick={() => close.current?.()}>
            <Icon name="close" />
          </button>
        </div>
      </div>
      {!folded && children}
    </aside>
  )
}

export default Dock
