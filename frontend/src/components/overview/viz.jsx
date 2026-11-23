/**
 * The overview's visualisation kit, hand-drawn SVG: one tooltip (pointer and keyboard alike, Escape
 * closes it), a series read day by day with the arrow keys, the small charts of the strip and the
 * cards, the table view each chart has, and the one-line empty state. Colours are tokens only
 * (--s0..--s3, --grad-a/--grad-b, states), so Atelier draws flat and Aurore in its gradient.
 */
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { Icon } from '../atelier'
import { toCsv } from '../../lib/overviewViz'

const domId = (raw) => `v${String(raw).replace(/[^a-zA-Z0-9_-]/g, '')}`

/**
 * The tooltip: `{title, rows: [{label, value, color?}], hint?}`, the value first in reading weight.
 * Fixed to the viewport beside its anchor, kept inside the window, flipped under it near the top.
 */
function ChartTip({ id, anchor, model }) {
  const ref = useRef(null)
  const [at, setAt] = useState(null)
  useLayoutEffect(() => {
    const box = anchor?.getBoundingClientRect?.()
    const el = ref.current
    if (!box || !el) return
    const tw = el.offsetWidth
    const th = el.offsetHeight
    let y = box.top - th - 10
    if (y < 8) y = box.bottom + 10
    const x = Math.max(8, Math.min(window.innerWidth - tw - 8, box.left + box.width / 2 - tw / 2))
    setAt({ left: x, top: y })
  }, [anchor, model])
  return createPortal(
    <div ref={ref} className={at ? 'chart-tip on' : 'chart-tip'} id={id} role="tooltip" data-testid="chart-tip"
      style={at || undefined}>
      {model.title && <h4>{model.title}</h4>}
      {(model.rows || []).map((r) => (
        <div className="row" key={r.label}>
          <span>{r.color && <i className="key" style={{ background: r.color }} />}{r.label}</span>
          <b>{r.value}</b>
        </div>
      ))}
      {model.hint && <div className="hint">{model.hint}</div>}
    </div>,
    document.body,
  )
}

/**
 * One tooltip per chart: `bind(model)` gives an element the pointer and focus handlers, `show` and `hide`
 * drive it by hand; `node` renders it. Escape hides an open tooltip before anything else hears the key.
 */
export function useChartTip(onEscape) {
  const id = domId(useId())
  const [tip, setTip] = useState(null)
  const escaped = useRef(onEscape)
  escaped.current = onEscape
  const show = useCallback((anchor, model) => {
    const m = typeof model === 'function' ? model() : model
    setTip(anchor && m ? { anchor, model: m } : null)
  }, [])
  const hide = useCallback(() => setTip(null), [])
  useEffect(() => {
    if (!tip) return undefined
    const key = (e) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      e.stopPropagation()
      setTip(null)
      escaped.current?.()
    }
    document.addEventListener('keydown', key, true)
    return () => document.removeEventListener('keydown', key, true)
  }, [tip])
  const bind = (model) => ({
    onPointerEnter: (e) => show(e.currentTarget, model),
    onPointerLeave: hide,
    onFocus: (e) => show(e.currentTarget, model),
    onBlur: hide,
    'aria-describedby': tip ? id : undefined,
  })
  return { id, show, hide, bind, open: Boolean(tip), node: tip ? <ChartTip id={id} anchor={tip.anchor} model={tip.model} /> : null }
}

/**
 * A series of marks read one at a time: the pointer over a mark or the arrow keys (Home, End) on the
 * focused chart move the cursor, Escape clears it, Enter picks the day; the tooltip follows the cursor.
 * `children({at, ref, enter})` draws the marks: `ref(i)` names mark i's element, `enter(i)` its hover.
 */
export function SeriesFrame({ count, label, className, tipModel, onPick, children }) {
  const [at, setAt] = useState(null)
  // Escape clears the cursor with the tooltip: the next render would otherwise show the tooltip again
  const tip = useChartTip(() => setAt(null))
  const els = useRef([])
  const { show, hide } = tip
  useEffect(() => {
    if (at === null || !els.current[at]) hide()
    else show(els.current[at], () => tipModel(at))
  }, [at, show, hide, tipModel])
  const onKeyDown = (e) => {
    const moves = { ArrowLeft: -1, ArrowRight: 1, ArrowDown: -1, ArrowUp: 1 }
    if (e.key === 'Home' || e.key === 'End') { e.preventDefault(); setAt(e.key === 'Home' ? 0 : count - 1); return }
    if (e.key === 'Escape' && at !== null) { e.preventDefault(); setAt(null); return }
    if ((e.key === 'Enter' || e.key === ' ') && at !== null && onPick) { e.preventDefault(); onPick(at); return }
    if (!(e.key in moves)) return
    e.preventDefault()
    setAt((cur) => Math.min(count - 1, Math.max(0, cur === null ? count - 1 : cur + moves[e.key])))
  }
  const ref = (i) => (el) => { els.current[i] = el }
  const enter = (i) => () => setAt(i)
  return (
    <div className={className} tabIndex={0} role="group" aria-label={label}
      aria-describedby={tip.open ? tip.id : undefined}
      onKeyDown={onKeyDown} onFocus={(e) => { if (e.target === e.currentTarget && at === null) setAt(count - 1) }}
      onBlur={() => setAt(null)} onPointerLeave={() => setAt(null)}>
      {children({ at, ref, enter })}
      {tip.node}
    </div>
  )
}

/**
 * Mirror bars, one day per slot: successes rise in the series colour, failures drop in red, so the
 * direction says the state and the colour confirms it; a day without operation is a grey dash.
 */
export function MirrorBars({ ok, failed, color, label, tipModel, onPick }) {
  const W = 300
  const H = 56
  const base = 38
  const count = ok.length
  const slot = W / Math.max(1, count)
  const bw = Math.min(7, slot - 2)
  const up = Math.max(1, ...ok)
  const down = Math.max(3, ...failed)
  return (
    <SeriesFrame className="mirror" count={count} label={label} tipModel={tipModel} onPick={onPick}>
      {({ at, ref, enter }) => (
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true" data-testid="mirror">
          <line className="base" x1="0" x2={W} y1={base} y2={base} vectorEffect="non-scaling-stroke" />
          {ok.map((v, i) => {
            const x = i * slot + (slot - bw) / 2
            const hu = (v / up) * (base - 4)
            const f = failed[i] || 0
            return (
              <g key={i} ref={ref(i)} data-day={i} className={at === i ? 'day on' : 'day'} onPointerEnter={enter(i)}
                onClick={onPick && f > 0 ? () => onPick(i) : undefined}>
                <rect className="hit" x={i * slot} y="0" width={slot} height={H} />
                {v > 0
                  ? <rect className="ok" x={x} y={base - 1 - hu} width={bw} height={hu} rx="1.5" style={{ fill: color }} />
                  : <rect className="idle" x={x} y={base - 2} width={bw} height="1.5" />}
                {f > 0 && <rect className="fail" x={x} y={base + 1} width={bw} height={Math.max(4, (f / down) * (H - base - 3))} rx="1.5" />}
              </g>
            )
          })}
        </svg>
      )}
    </SeriesFrame>
  )
}

/** Gradient grad-a to grad-b along x (flat in Atelier, where both are the accent). */
function Gradient({ id, x2, y2 = 0 }) {
  return (
    <defs>
      <linearGradient id={id} gradientUnits="userSpaceOnUse" x1="0" y1={y2} x2={x2} y2="0">
        <stop offset="0" className="grad-a" /><stop offset="1" className="grad-b" />
      </linearGradient>
    </defs>
  )
}

/** The strip's trend: a 2 px line in the retreat grey, a wash under it, the last day as an accent point. */
export function Spark({ values, label, w = 120, h = 34 }) {
  const gid = domId(useId())
  const max = Math.max(1, ...values)
  const pad = 4
  const count = values.length
  const x = (i) => (count > 1 ? pad + (i * (w - pad * 2)) / (count - 1) : w / 2)
  const y = (v) => h - pad - (v / max) * (h - pad * 2)
  const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  return (
    <svg className="spark-trend" viewBox={`0 0 ${w} ${h}`} width={w} height={h} role="img" aria-label={label}>
      <Gradient id={gid} x2={w} />
      <polygon className="spark-wash" points={`${x(0)},${h - pad} ${pts} ${x(count - 1)},${h - pad}`} fill={`url(#${gid})`} />
      <polyline className="spark-line" points={pts} />
      <circle className="spark-now" cx={x(count - 1)} cy={y(values[count - 1] || 0)} r="4" />
    </svg>
  )
}

/** Columns for rare counts: the past in the retreat grey, today in `tone`; a day at zero is a tick. */
export function MiniBars({ values, label, tone = 'var(--accent)', w = 100, h = 34 }) {
  const max = Math.max(1, ...values)
  const pad = 4
  const slot = (w - pad * 2) / Math.max(1, values.length)
  const bw = Math.max(3, slot - 2)
  const y = (v) => h - pad - (v / max) * (h - pad * 2)
  return (
    <svg className="mini-bars" viewBox={`0 0 ${w} ${h}`} width={w} height={h} role="img" aria-label={label}>
      {values.map((v, i) => {
        const last = i === values.length - 1
        return (
          <rect key={i} className={last ? 'bar now' : 'bar'} x={pad + i * slot} y={v ? y(v) : h - pad - 1.5} width={bw}
            height={v ? h - pad - y(v) : 1.5} rx="1.5" style={{ fill: last ? tone : 'var(--s0)' }} />
        )
      })}
    </svg>
  )
}

/** One whole in parts side by side (a thin bar), each part at least visible; `parts` [{key, value, color}]. */
export function SplitBar({ parts, label, className = 'split-bar' }) {
  const shown = parts.filter((p) => p.value > 0)
  return (
    <span className={className} role="img" aria-label={label}>
      {shown.map((p) => <i key={p.key} data-part={p.key} style={{ flexGrow: p.value, background: p.color }} />)}
    </span>
  )
}

/** One ratio out of 100 as a ring: a track in a light step of the accent, the arc in grad-a to grad-b. */
export function Ring({ value, label, size = 176, stroke = 12, children }) {
  const gid = domId(useId())
  const r = (size - stroke) / 2 - 2
  const c = 2 * Math.PI * r
  const len = (c * Math.max(0, Math.min(100, value))) / 100
  const mid = size / 2
  return (
    <div className="ring-wrap">
      <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label}>
        <Gradient id={gid} x2={size} y2={size} />
        <circle className="ring-track" cx={mid} cy={mid} r={r} fill="none" strokeWidth={stroke} />
        {len > 0 && (
          <circle className="ring-arc" cx={mid} cy={mid} r={r} fill="none" stroke={`url(#${gid})`} strokeWidth={stroke}
            strokeLinecap="round" transform={`rotate(-90 ${mid} ${mid})`} strokeDasharray={`${len} ${c}`}
            style={{ '--len': len }} data-value={value} />
        )}
      </svg>
      <div className="ring-center">{children}</div>
    </div>
  )
}

/** A chart's figures as a table, for a screen reader and for export: `tables` [{caption, columns, rows}]. */
export function ChartTable({ tables, filename }) {
  const { t } = useTranslation()
  const download = () => {
    const text = tables.map((tb) => `${tb.caption}\r\n${toCsv(tb.columns, tb.rows)}`).join('\r\n')
    if (typeof URL.createObjectURL !== 'function') return
    const url = URL.createObjectURL(new Blob([`﻿${text}`], { type: 'text/csv;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${filename}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }
  return (
    <div className="panel-content chart-table">
      {tables.map((tb) => (
        <table key={tb.caption} className="viz-table">
          <caption>{tb.caption}</caption>
          <thead><tr>{tb.columns.map((c, i) => <th key={c} scope="col" className={i > 0 ? 'num' : undefined}>{c}</th>)}</tr></thead>
          <tbody>
            {tb.rows.map((r, ri) => (
              <tr key={ri}>{r.map((v, i) => (i === 0 ? <th key={i} scope="row">{v}</th> : <td key={i} className="num">{v}</td>))}</tr>
            ))}
          </tbody>
        </table>
      ))}
      <button type="button" className="btn" data-action="export-csv" onClick={download}>
        <Icon name="download" /><span>{t('overview.viz.downloadCsv')}</span>
      </button>
    </div>
  )
}

/** The one-line empty state: an icon, a sentence, the useful action after it. */
export function EmptyLine({ icon = 'check', text, children }) {
  return (
    <p className="empty-line" role="status">
      <Icon name={icon} /><span>{text}</span>{children}
    </p>
  )
}
