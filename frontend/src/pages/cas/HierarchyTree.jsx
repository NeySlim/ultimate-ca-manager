/**
 * CAs page: the trust hierarchy as a tree. A root that heads a subtree is a card with its
 * branches on its right; a root alone is one compact line; roots with neither a sub-authority
 * nor a certificate fold into one group once they are many. One `role="tree"`, one tab stop.
 */
import { useState, useMemo, useRef, useEffect, useLayoutEffect, useId } from 'react'
import { ShieldCheck, TreeStructure, CaretDown, CaretRight, ArrowsInSimple, ArrowsOutSimple } from '@phosphor-icons/react'
import { ListButton } from '../../components/list'
import { cn, formatDate } from '../../lib/utils'
import { layoutRoots, nameOfCA } from './caTree'
import { CAStatePill, CAMarks } from './CAState'
import './hierarchy.css'

const IDLE = 'idle'
// Compact lines drawn at once in a group; the rest comes on demand
const COMPACT_PAGE = 120

/** "12 certificates" with its number set apart, whatever the language puts around it. */
function Count({ text }) {
  const m = /^(\D*)(\d[\d\s.,  ]*)(.*)$/.exec(text)
  if (!m) return <span>{text}</span>
  return <span>{m[1]}<strong>{m[2].trim()}</strong> {m[3].trim()}</span>
}

export function HierarchyTree({ forest, query = '', filtered = false, crossLinks = [], selectedId, onSelect, t }) {
  const baseId = useId().replace(/:/g, '')
  const treeRef = useRef(null)
  const forestRef = useRef(null)
  // A search or a tab view shows the branches down to what it kept
  const searching = filtered || !!query.trim()
  // What the user folded or unfolded; everything else follows the default below
  const [overrides, setOverrides] = useState(() => new Map())
  const [focusKey, setFocusKey] = useState(null)
  const [limit, setLimit] = useState(COMPACT_PAGE)
  const [paths, setPaths] = useState([])

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

  // The authority open in the detail is never left inside a folded branch
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

  // The keys on screen, in order: the first one is the tab stop until another takes the focus
  const visible = []
  const walk = (ca) => { visible.push(ca.id); if (isOpen(ca.id)) kidsOf(ca).forEach(walk) }
  branches.forEach(walk)
  shownCompact.forEach((ca) => visible.push(ca.id))
  if (idle.length) { visible.push(IDLE); if (isOpen(IDLE)) shownIdle.forEach((ca) => visible.push(ca.id)) }
  const tabStop = visible.includes(focusKey) ? focusKey : visible[0]

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
      else onSelect?.(forest.byId.get(key))
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

  // Cross-certificate links are measured after layout: card heights and positions vary
  useLayoutEffect(() => {
    const box = forestRef.current
    if (!box) return undefined
    const measure = () => {
      const f = box.getBoundingClientRect()
      const next = crossLinks.map(({ from, to }, n) => {
        const a = box.querySelector(`[data-ca="${from}"]`)
        const b = box.querySelector(`[data-ca="${to}"]`)
        if (!a || !b) return null
        const ra = a.getBoundingClientRect()
        const rb = b.getBoundingClientRect()
        const at = branches.findIndex((c) => c.id === from)
        const stacked = at >= 0 && branches[at + 1]?.id === to && rb.top >= ra.bottom
        if (stacked) {
          const x = Math.round(ra.left - f.left + 28)
          const y1 = Math.round(ra.bottom - f.top)
          const y2 = Math.round(rb.top - f.top - 3)
          return { from, to, d: `M${x} ${y1}V${y2}`, label: [x + 12, Math.round((y1 + y2) / 2) + 4] }
        }
        const gutter = 5 + (n % 3) * 4
        const ya = Math.round(ra.top - f.top + 23)
        const yb = Math.round(rb.top - f.top + 23)
        return { from, to, d: `M${Math.round(ra.left - f.left)} ${ya}H${gutter}V${yb}H${Math.round(rb.left - f.left - 3)}` }
      }).filter(Boolean)
      setPaths((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next))
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(measure)
    observer.observe(box)
    return () => observer.disconnect()
  }, [crossLinks, branches, overrides, searching])

  const itemProps = (key, level, labelId, metaId) => ({
    role: 'treeitem',
    id: `${baseId}-node-${key}`,
    'data-node': key,
    'aria-level': level,
    'aria-labelledby': labelId,
    'aria-describedby': metaId,
    tabIndex: tabStop === key ? 0 : -1,
    onFocus: (e) => { if (e.target === e.currentTarget) setFocusKey(key) },
  })
  const counts = (ca) => {
    const subs = (forest.allKids.get(ca.id) || []).length
    return (
      <>
        <Count text={t('cas.certificateCount', { count: ca.certs || 0 })} />
        {subs > 0 && <Count text={t('cas.tree.subCaCount', { count: subs })} />}
      </>
    )
  }

  const card = (ca) => {
    const kids = kidsOf(ca)
    const open = kids.length > 0 && isOpen(ca.id)
    const name = nameOfCA(ca) || t('cas.unnamedCA')
    const level = forest.levelOf.get(ca.id)
    const labelId = `${baseId}-name-${ca.id}`
    const metaId = `${baseId}-meta-${ca.id}`
    const Icon = ca.type === 'root' ? ShieldCheck : TreeStructure
    return (
      <li
        key={ca.id}
        className="ca-node"
        aria-selected={selectedId === ca.id}
        aria-expanded={kids.length ? open : undefined}
        {...itemProps(ca.id, level, labelId, metaId)}
      >
        <div
          className={cn('ca-card', selectedId === ca.id && 'is-active', ca.status === 'Revoked' && 'is-revoked')}
          data-ca={ca.id}
          onClick={() => onSelect?.(ca)}
        >
          <div className="ca-card-head">
            <Icon aria-hidden="true" />
            <strong id={labelId} title={ca.subject || undefined}>{name}</strong>
            {kids.length > 0 && (
              <button
                type="button"
                className="ca-toggle"
                tabIndex={-1}
                aria-expanded={open}
                aria-label={t(open ? 'cas.tree.collapse' : 'cas.tree.expand', { name })}
                onClick={(e) => { e.stopPropagation(); toggle(ca.id) }}
              >
                {open ? <CaretDown aria-hidden="true" /> : <CaretRight aria-hidden="true" />}
              </button>
            )}
          </div>
          <span className="ca-purpose">
            {t(ca.type === 'root' ? 'common.rootCA' : 'common.intermediateCA')} · {t('cas.tree.level', { level })}
          </span>
          <div id={metaId} className="ca-meta">
            <div className="ca-badges">
              <CAStatePill ca={ca} t={t} />
              <CAMarks ca={ca} t={t} orphan={forest.orphans.has(ca.id)} />
            </div>
            <div className="ca-count">{counts(ca)}</div>
          </div>
        </div>
        {open && <ul role="group" className="ca-group">{kids.map(card)}</ul>}
      </li>
    )
  }

  const line = (ca, level) => {
    const name = nameOfCA(ca) || t('cas.unnamedCA')
    const labelId = `${baseId}-name-${ca.id}`
    const metaId = `${baseId}-meta-${ca.id}`
    const Icon = ca.type === 'root' ? ShieldCheck : TreeStructure
    const end = ca.valid_to || ca.not_after
    return (
      <li key={ca.id} className="ca-node is-compact" aria-selected={selectedId === ca.id} {...itemProps(ca.id, level, labelId, metaId)}>
        <div className={cn('ca-line', selectedId === ca.id && 'is-active')} data-ca={ca.id} onClick={() => onSelect?.(ca)}>
          <Icon aria-hidden="true" />
          <strong id={labelId} title={ca.subject || name}>{name}</strong>
          <span id={metaId} className="ca-line-meta">
            <CAMarks ca={ca} t={t} orphan={forest.orphans.has(ca.id)} compact />
            <CAStatePill ca={ca} t={t} />
            {ca.certs > 0 && <span className="ca-line-count">{t('cas.certificateCount', { count: ca.certs })}</span>}
            {end && <time className="ca-line-date" dateTime={String(end)}>{formatDate(end, { time: false })}</time>}
          </span>
        </div>
      </li>
    )
  }

  const more = (shown, all) => all.length > shown.length && (
    <div className="ca-more">
      <ListButton small onClick={() => setLimit((n) => n + COMPACT_PAGE)}>
        {t('cas.tree.showMore', { count: Math.min(COMPACT_PAGE, all.length - shown.length) })}
      </ListButton>
    </div>
  )

  const titleId = `${baseId}-title`
  const shown = branches.length + compact.length + idle.length
  const idleOpen = idle.length > 0 && isOpen(IDLE)

  return (
    <section className="ca-tree-panel" aria-labelledby={titleId}>
      <header className="ca-tree-head">
        <div>
          <h2 id={titleId}>{t('cas.tree.title')}</h2>
          <p>{t('cas.tree.hint')}</p>
        </div>
        {(foldable.length > 0 || idle.length > 0) && (
          <ListButton icon={anyOpen ? ArrowsInSimple : ArrowsOutSimple} onClick={toggleAll}>
            {t(anyOpen ? 'cas.tree.collapseAll' : 'cas.tree.expandAll')}
          </ListButton>
        )}
      </header>
      {shown === 0 ? (
        <p className="ca-empty" role="status">{t('cas.tree.noMatch')}</p>
      ) : (
        <div className="ca-tree" role="tree" aria-labelledby={titleId} ref={treeRef} onKeyDown={onKeyDown}>
          {branches.length > 0 && (
            <div className="ca-tree-scroll" role="presentation">
              <div className={cn('ca-forest', crossLinks.length > 0 && 'has-links')} ref={forestRef} role="presentation">
                <ul className="ca-branches" role="presentation">{branches.map(card)}</ul>
                {paths.length > 0 && (
                  <svg className="ca-cross-layer" aria-hidden="true" focusable="false">
                    <defs>
                      <marker id={`${baseId}-head`} viewBox="0 0 8 8" refX="6" refY="4" markerWidth="7" markerHeight="7" orient="auto">
                        <path d="M1 1L6 4L1 7" />
                      </marker>
                    </defs>
                    {paths.map((p) => (
                      <g key={`${p.from}-${p.to}`} data-cross-link={`${p.from}-${p.to}`}>
                        <path d={p.d} markerEnd={`url(#${baseId}-head)`} />
                        {p.label && <text x={p.label[0]} y={p.label[1]}>{t('cas.tree.crossLink')}</text>}
                      </g>
                    ))}
                  </svg>
                )}
              </div>
            </div>
          )}
          {shownCompact.length > 0 && (
            <ul className="ca-lines" role="presentation">{shownCompact.map((ca) => line(ca, 1))}</ul>
          )}
          {more(shownCompact, compact)}
          {idle.length > 0 && (
            <ul className="ca-bundles" role="presentation">
              <li
                className="ca-node ca-bundle"
                aria-expanded={idleOpen}
                {...itemProps(IDLE, 1, `${baseId}-idle`, undefined)}
              >
                <div className="ca-bundle-head" onClick={() => toggle(IDLE)}>
                  {idleOpen ? <CaretDown aria-hidden="true" /> : <CaretRight aria-hidden="true" />}
                  <span id={`${baseId}-idle`}>{t('cas.tree.idleRoots', { count: idle.length })}</span>
                </div>
                {idleOpen && (
                  <>
                    <ul className="ca-lines" role="group">{shownIdle.map((ca) => line(ca, 2))}</ul>
                    {more(shownIdle, idle)}
                  </>
                )}
              </li>
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

export default HierarchyTree
