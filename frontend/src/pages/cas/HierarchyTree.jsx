/**
 * CAs page: the trust hierarchy of the mockup's caView() (panel, heading, forest of ca-card nodes,
 * the dotted cross-certificate link, the guidance). A root that heads a subtree is a card with its
 * branches on its right; a root alone is one compact line; roots with neither a sub-authority nor a
 * certificate fold into one group once they are many. One `role="tree"`, one tab stop.
 */
import { useState, useMemo, useRef, useEffect, useLayoutEffect } from 'react'
import { Icon } from '../../components/atelier'
import { useMobile } from '../../contexts/MobileContext'
import { formatDate } from '../../lib/utils'
import { layoutRoots, nameOfCA } from './caTree'
import { CAStatePill, CAMarks } from './CAState'

const IDLE = 'idle'
// Compact lines drawn at once in a group; the rest comes on demand
const COMPACT_PAGE = 120

/** « 12 certificats » as the mockup's ca-count draws it: the number (<0>…</0> in the text) in bold, its word after. */
function Count({ text }) {
  const m = /^(.*)<0>(.*)<\/0>(.*)$/.exec(text) || /^(\D*)(\d[\d\s.,]*)(.*)$/.exec(text)
  if (!m) return <span>{text}</span>
  return <span>{m[1]}<strong>{m[2].trim()}</strong>{m[3].trim()}</span>
}

export function HierarchyTree({ forest, query = '', filtered = false, crossLinks = [], selectedId, onSelect, onReset, total, t }) {
  const { isMobile } = useMobile()
  const treeRef = useRef(null)
  const forestRef = useRef(null)
  // A search or a tab view shows the branches down to what it kept
  const searching = filtered || !!query.trim()
  // What the user folded or unfolded; everything else follows the default below
  const [overrides, setOverrides] = useState(() => new Map())
  const [focusKey, setFocusKey] = useState(null)
  const [limit, setLimit] = useState(COMPACT_PAGE)
  const [links, setLinks] = useState([])

  const { branches, compact, idle } = useMemo(() => {
    const linked = new Set(crossLinks.flatMap((l) => [l.from, l.to]))
    const layout = layoutRoots(forest, { query, linked })
    // The root a cross-certificate was issued to sits right under the one that issued it
    const list = [...layout.branches]
    for (const { from, to } of crossLinks) {
      const i = list.findIndex((c) => c.id === from)
      const j = list.findIndex((c) => c.id === to)
      if (i < 0 || j < 0 || j === i + 1) continue
      const [moved] = list.splice(j, 1)
      list.splice(list.findIndex((c) => c.id === from) + 1, 0, moved)
    }
    return { ...layout, branches: list }
  }, [forest, query, crossLinks])

  // Roots open on their first level, deeper nodes stay folded
  const isOpen = (key) => (overrides.has(key) ? overrides.get(key) : key !== IDLE && (searching || forest.levelOf.get(key) === 1))
  const toggle = (key) => setOverrides((prev) => new Map(prev).set(key, !isOpen(key)))
  const kidsOf = (ca) => forest.kids.get(ca.id) || []

  // The authority shown beside the tree is never left inside a folded branch
  const idleIndex = idle.findIndex((c) => c.id === selectedId)
  useEffect(() => {
    if (selectedId === null || selectedId === undefined) return
    setOverrides((prev) => {
      const next = new Map(prev)
      for (let p = forest.parentOf.get(selectedId); p !== undefined; p = forest.parentOf.get(p)) next.set(p, true)
      if (idleIndex >= 0) next.set(IDLE, true)
      return [...next].every(([k, v]) => prev.get(k) === v) ? prev : next
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, idleIndex >= 0])

  const compactIndex = compact.findIndex((c) => c.id === selectedId)
  const shownCompact = compact.slice(0, Math.max(limit, compactIndex + 1))
  const shownIdle = idle.slice(0, Math.max(limit, idleIndex + 1))

  // The keys on screen, in order: the selected one is the tab stop, as in the mockup, until another takes the focus
  const visible = []
  const walk = (ca) => { visible.push(ca.id); if (isOpen(ca.id)) kidsOf(ca).forEach(walk) }
  branches.forEach(walk)
  shownCompact.forEach((ca) => visible.push(ca.id))
  if (idle.length) { visible.push(IDLE); if (isOpen(IDLE)) shownIdle.forEach((ca) => visible.push(ca.id)) }
  const tabStop = visible.includes(focusKey) ? focusKey : visible.includes(selectedId) ? selectedId : visible[0]

  const foldable = [...forest.kids.keys()]
  const anyOpen = foldable.some(isOpen) || (idle.length > 0 && isOpen(IDLE))
  const toggleAll = () => setOverrides(new Map([
    ...foldable.map((id) => [id, !anyOpen]),
    // Unfolding everything leaves the idle group as it is: it is not part of a hierarchy
    ...(anyOpen ? [[IDLE, false]] : overrides.has(IDLE) ? [[IDLE, overrides.get(IDLE)]] : []),
  ]))

  const keyOf = (el) => (el.dataset.node === IDLE ? IDLE : Number(el.dataset.node))
  const onKeyDown = (e) => {
    const el = e.target
    if (el.getAttribute('role') !== 'treeitem') return
    if (!['ArrowDown', 'ArrowUp', 'ArrowRight', 'ArrowLeft', 'Home', 'End', 'Enter', ' '].includes(e.key)) return
    e.preventDefault()
    const items = [...treeRef.current.querySelectorAll('[role="treeitem"]')]
    const i = items.indexOf(el)
    const key = keyOf(el)
    const foldableItem = el.hasAttribute('aria-expanded')
    const open = el.getAttribute('aria-expanded') === 'true'
    let next
    if (e.key === 'Enter' || e.key === ' ') {
      if (key === IDLE) toggle(IDLE)
      else onSelect?.(forest.byId.get(key), { keyboard: true })
      return
    }
    if (e.key === 'ArrowDown') next = items[i + 1]
    else if (e.key === 'ArrowUp') next = items[i - 1]
    else if (e.key === 'Home') next = items[0]
    else if (e.key === 'End') next = items[items.length - 1]
    else if (e.key === 'ArrowRight') {
      if (foldableItem && !open) { toggle(key); return }
      if (open) next = el.querySelector('[role="treeitem"]')
    } else if (e.key === 'ArrowLeft') {
      if (open) { toggle(key); return }
      next = el.parentElement?.closest('[role="treeitem"]')
    }
    if (next) { setFocusKey(keyOf(next)); next.focus() }
  }

  // The mockup's drawCrossLink(): measured after layout, a dotted line under the issuer's card down to the
  // card it cross-certified (`below`), or in the left gutter on a phone and between cards that are not stacked
  useLayoutEffect(() => {
    const box = forestRef.current
    if (!box) return undefined
    const measure = () => {
      const f = box.getBoundingClientRect()
      const next = crossLinks.map(({ from, to }) => {
        const a = box.querySelector(`[data-ca="${from}"]`)
        const b = box.querySelector(`[data-ca="${to}"]`)
        if (!a || !b) return null
        const ra = a.getBoundingClientRect()
        const rb = b.getBoundingClientRect()
        const at = branches.findIndex((c) => c.id === from)
        const stacked = at >= 0 && branches[at + 1]?.id === to && rb.top >= ra.bottom
        if (stacked && !isMobile) {
          return { from, to, kind: 'below', style: { left: `${ra.left - f.left + 28}px`, top: `${ra.bottom - f.top}px`, height: `${Math.max(0, rb.top - ra.bottom)}px` } }
        }
        const [top, bottom] = ra.top <= rb.top ? [ra, rb] : [rb, ra]
        return { from, to, kind: 'gutter', style: { left: `${Math.min(ra.left, rb.left) - f.left - 10}px`, top: `${top.top - f.top + 22}px`, height: `${bottom.top - top.top}px` } }
      }).filter(Boolean)
      setLinks((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next))
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(measure)
    observer.observe(box)
    return () => observer.disconnect()
  }, [crossLinks, branches, overrides, searching, isMobile])

  const itemProps = (key, level, labelId, metaId) => ({
    role: 'treeitem',
    id: `ca-node-${key}`,
    'data-node': key,
    'aria-level': level,
    'aria-labelledby': labelId,
    'aria-describedby': metaId,
    tabIndex: tabStop === key ? 0 : -1,
    onFocus: (e) => { if (e.target === e.currentTarget) setFocusKey(key) },
  })

  const card = (ca) => {
    const kids = kidsOf(ca)
    const open = kids.length > 0 && isOpen(ca.id)
    const subs = (forest.allKids.get(ca.id) || []).length
    const n = ca.certs || 0
    const name = nameOfCA(ca) || t('cas.unnamedCA')
    const level = forest.levelOf.get(ca.id)
    const selected = selectedId === ca.id
    const revoked = ca.status === 'Revoked' || ca.revoked
    return (
      <li key={ca.id} className="ca-node" aria-selected={selected} aria-expanded={kids.length ? open : undefined}
        {...itemProps(ca.id, level, `ca-name-${ca.id}`, `ca-meta-${ca.id}`)}>
        <div className={`ca-card ${selected ? 'active' : ''} state-${revoked ? 'revoked' : 'active'}`} data-ca={ca.id}
          onClick={() => onSelect?.(ca)}>
          <div className="ca-card-head">
            <Icon name={ca.type === 'root' ? 'shield' : 'branch'} />
            <strong id={`ca-name-${ca.id}`} title={ca.subject || undefined}>{name}</strong>
            {kids.length > 0 && (
              <button type="button" className="icon-btn tree-toggle" id={`ca-toggle-${ca.id}`} tabIndex={-1} aria-expanded={open}
                aria-label={t(open ? 'cas.tree.collapse' : 'cas.tree.expand', { name })}
                onClick={(e) => { e.stopPropagation(); toggle(ca.id) }}>
                <Icon name={open ? 'down' : 'right'} />
              </button>
            )}
          </div>
          <span className="ca-purpose">{t(ca.type === 'root' ? 'common.rootCA' : 'common.intermediateCA')} · {t('cas.tree.level', { level })}</span>
          <div className="ca-badges" id={`ca-meta-${ca.id}`}>
            <CAStatePill ca={ca} t={t} />
            <CAMarks ca={ca} t={t} orphan={forest.orphans.has(ca.id)} />
            <span className="sr-only">
              , {t('cas.certificateCount', { count: n })}{subs > 0 && <>, {t('cas.tree.subCaCount', { count: subs })}</>}
            </span>
          </div>
          <div className="ca-count" aria-hidden="true">
            <Count text={t('cas.tree.certCount', { count: n })} />
            {subs > 0 && <Count text={t('cas.tree.subCount', { count: subs })} />}
          </div>
        </div>
        {open && <ul role="group" className="ca-group">{kids.map(card)}</ul>}
      </li>
    )
  }

  // A lone root on one line (a gabarit of the product, extensions.css): the card's facts in a row
  const line = (ca, level) => {
    const name = nameOfCA(ca) || t('cas.unnamedCA')
    const end = ca.valid_to || ca.not_after
    const selected = selectedId === ca.id
    return (
      <li key={ca.id} className="ca-node" aria-selected={selected} {...itemProps(ca.id, level, `ca-name-${ca.id}`, `ca-meta-${ca.id}`)}>
        <div className={`ca-line ${selected ? 'active' : ''}`} data-ca={ca.id} onClick={() => onSelect?.(ca)}>
          <Icon name={ca.type === 'root' ? 'shield' : 'branch'} />
          <strong id={`ca-name-${ca.id}`} title={ca.subject || name}>{name}</strong>
          <span className="ca-badges" id={`ca-meta-${ca.id}`}>
            <CAStatePill ca={ca} t={t} />
            <CAMarks ca={ca} t={t} orphan={forest.orphans.has(ca.id)} />
            {ca.certs > 0 && <span className="ca-line-count">{t('cas.certificateCount', { count: ca.certs })}</span>}
            {end && <time className="ca-line-date" dateTime={String(end)}>{formatDate(end, { time: false })}</time>}
          </span>
        </div>
      </li>
    )
  }

  const more = (shown, all) => all.length > shown.length && (
    <li role="none" className="ca-more">
      <button type="button" className="btn" onClick={() => setLimit((n) => n + COMPACT_PAGE)}>
        {t('cas.tree.showMore', { count: Math.min(COMPACT_PAGE, all.length - shown.length) })}
      </button>
    </li>
  )

  const shown = branches.length + compact.length + idle.length
  const idleOpen = idle.length > 0 && isOpen(IDLE)

  return (
    <section className="panel ca-tree-panel" aria-labelledby="ca-tree-title">
      <header className="panel-heading">
        <div>
          <h2 id="ca-tree-title">{t('cas.tree.title')}</h2>
          <p>{t('cas.tree.hint')}</p>
        </div>
        <div className="actions">
          <span className="chip"><Icon name="branch" />{t('cas.total', { count: total ?? forest.byId.size })}</span>
          {(foldable.length > 0 || idle.length > 0) && (
            <button type="button" className="btn" id="ca-toggle-all" data-action="ca-toggle-all" onClick={toggleAll}>
              <Icon name={anyOpen ? 'minimize' : 'expand'} />{t(anyOpen ? 'cas.tree.collapseAll' : 'cas.tree.expandAll')}
            </button>
          )}
        </div>
      </header>
      {shown === 0 ? (
        <div className="empty" role="status">
          <Icon name="search" />
          <h3>{t('cas.tree.noMatch')}</h3>
          <p>{t('cas.tree.noMatchHint')}</p>
          {onReset && <button type="button" className="btn" data-action="reset-filters" onClick={onReset}>{t('cas.tree.reset')}</button>}
        </div>
      ) : (
        <div className="ca-tree-scroll" id="ca-tree-scroll">
          <div className="ca-forest" ref={forestRef}>
            <ul className="ca-tree" id="ca-tree" role="tree" aria-labelledby="ca-tree-title" ref={treeRef} onKeyDown={onKeyDown}>
              {branches.map(card)}
              {shownCompact.length > 0 && (
                <li role="none" className="ca-compact">
                  <ul role="group" className="ca-lines">
                    {shownCompact.map((ca) => line(ca, 1))}
                    {more(shownCompact, compact)}
                  </ul>
                </li>
              )}
              {idle.length > 0 && (
                <li className="ca-node ca-bundle" aria-expanded={idleOpen} {...itemProps(IDLE, 1, 'ca-name-idle', undefined)}>
                  <div className="ca-bundle-head" onClick={() => toggle(IDLE)}>
                    <Icon name={idleOpen ? 'down' : 'right'} />
                    <span id="ca-name-idle">{t('cas.tree.idleRoots', { count: idle.length })}</span>
                  </div>
                  {idleOpen && (
                    <ul role="group" className="ca-lines">
                      {shownIdle.map((ca) => line(ca, 2))}
                      {more(shownIdle, idle)}
                    </ul>
                  )}
                </li>
              )}
            </ul>
            {links.map((l) => (
              <div key={`${l.from}-${l.to}`} className={`cross-link ${l.kind}`} data-cross-link={`${l.from}-${l.to}`} aria-hidden="true" style={l.style}>
                <span>{t('cas.tree.crossLink')}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <p className="ca-guidance">
        <Icon name="lock" /> <strong>{t('cas.guidance.lead')}</strong> {t('cas.guidance.offline')}
        {crossLinks.length > 0 && <> {t('cas.guidance.cross')}</>}
      </p>
    </section>
  )
}

export default HierarchyTree
