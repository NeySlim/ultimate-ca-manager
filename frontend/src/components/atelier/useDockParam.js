/**
 * The object a dock shows and its section, kept in the URL as the mockup keeps them (`item`, its
 * inspector `tab`, M:134-161): `?item=<id>&section=<id>`. `tab` already names the sub-view of
 * several pages, so the section takes `section`. Opening adds a history step, so Back closes the
 * dock; a section change or another object replaces it; closing a dock opened here steps back.
 * A dock with several open objects (`list`) also keeps them, as the mockup's `open=1,2,3`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useLatestLocation } from './useLatestLocation'

export const ITEM_PARAM = 'item'
export const SECTION_PARAM = 'section'
export const LIST_PARAM = 'open'
const NONE = []
// The mark of a history step this hook added, holding the page's own parameters at that point:
// closing steps back only while they are unchanged, so a sort or filter set meanwhile is kept
const OPENED = 'ucmDockOpened'

const sameId = (a, b) => a != null && b != null && String(a) === String(b)
/** The URL's id as the API's records hold it: a number when it is one */
export const asId = (v) => (typeof v === 'string' && /^\d+$/.test(v) ? Number(v) : v)

/**
 * @param {object} [o]
 * @param {string[]} [o.sections]  the section ids; another value in the URL reads as `fallback`
 * @param {string} [o.fallback]  the first section, left out of the URL
 * @param {string[]} [o.aliases]  former names of the object in incoming links (`selected`, `request`)
 * @param {boolean} [o.list]  the dock holds several objects: their ids live in `open` once there are two
 */
export function useDockParam({ sections, fallback = 'overview', aliases = [], list: withList = false } = {}) {
  const [params] = useSearchParams()
  const latest = useLatestLocation()
  const navigate = useNavigate()
  const names = [ITEM_PARAM, ...aliases]
  const item = names.map((n) => params.get(n)).find((v) => v) ?? null
  const raw = params.get(SECTION_PARAM)
  const section = item && raw && (!sections || sections.includes(raw)) ? raw : fallback
  const listRaw = withList ? params.get(LIST_PARAM) : null
  const list = useMemo(() => (listRaw ? [...new Set(listRaw.split(',').filter(Boolean))] : NONE), [listRaw])

  const aliasKey = aliases.join(',')
  // The URL as it is now, a write since the last render included (another hook's, or this one's in the same handler)
  const now = useCallback(() => {
    const loc = latest()
    const p = new URLSearchParams(loc.search)
    const at = [ITEM_PARAM, ...aliasKey.split(',').filter(Boolean)].map((n) => p.get(n)).find((v) => v) ?? null
    return { params: p, location: loc, item: at }
  }, [latest, aliasKey])

  // The URL's parameters that are not the dock's, in a stable order
  const pageOf = useCallback((search) => {
    const p = new URLSearchParams(search)
    for (const n of [ITEM_PARAM, SECTION_PARAM, ...aliasKey.split(',').filter(Boolean)]) p.delete(n)
    if (withList) p.delete(LIST_PARAM)
    return [...p.entries()].map(([k, v]) => `${k}=${v}`).sort().join('&')
  }, [aliasKey, withList])

  const write = useCallback((patch, { push = false } = {}) => {
    const { params: cur, location: loc } = now()
    const next = new URLSearchParams(cur)
    for (const n of [ITEM_PARAM, ...aliasKey.split(',').filter(Boolean)]) next.delete(n)
    next.delete(SECTION_PARAM)
    const kept = next.get(LIST_PARAM)
    if (withList) next.delete(LIST_PARAM)
    if (patch.item != null) next.set(ITEM_PARAM, String(patch.item))
    if (patch.item != null && patch.section && patch.section !== fallback) next.set(SECTION_PARAM, patch.section)
    // No object open, no list; a write without one keeps the URL's; a single object is `item` alone
    if (withList && patch.item != null) {
      const ids = patch.list ? patch.list.map(String) : kept ? kept.split(',') : []
      if (ids.length > 1) next.set(LIST_PARAM, ids.join(','))
    }
    const qs = next.toString()
    const to = { pathname: loc.pathname, search: qs ? `?${qs}` : '', hash: loc.hash }
    const state = push ? { ...(loc.state || {}), [OPENED]: pageOf(loc.search) } : loc.state
    navigate(to, { replace: !push, state })
  }, [navigate, now, fallback, aliasKey, withList, pageOf])

  const open = useCallback((id, { section: asked, list: ids } = {}) => {
    if (id == null) return
    const { item: cur, params: p } = now()
    const keep = sameId(cur, id) && !asked ? p.get(SECTION_PARAM) : asked
    write({ item: id, section: keep, list: ids }, { push: cur == null })
  }, [write, now])

  // The entry a step back is leaving: the browser moves back later, a second close meanwhile does nothing
  const leaving = useRef(null)
  const drawnKey = useLocation().key
  useEffect(() => { leaving.current = null }, [drawnKey])
  const close = useCallback(() => {
    const { item: cur, location: loc } = now()
    if (cur == null || (loc.key && leaving.current === loc.key)) return
    const mark = loc.state?.[OPENED]
    if (typeof mark === 'string' && loc.key !== 'default' && mark === pageOf(loc.search)) {
      leaving.current = loc.key
      navigate(-1)
    } else write({})
  }, [navigate, write, now, pageOf])

  const setSection = useCallback((id) => {
    const cur = now().item
    if (cur != null) write({ item: cur, section: id })
  }, [write, now])

  // The open objects changed, the shown one did not
  const setList = useCallback((ids) => {
    const { item: cur, params: p } = now()
    if (cur != null) write({ item: cur, section: p.get(SECTION_PARAM), list: ids })
  }, [write, now])

  return { item, section, list, open, close, setSection, setList }
}

/**
 * A page's open object held by the URL, in place of `useState(null)`: `select(obj)` opens it,
 * `select(null)` closes. The object is the one last selected while its id is the URL's, else the
 * list's row, else `load(id)` once the list is `ready`; an id found nowhere leaves the URL.
 */
export function useDockSelection(items, { key = (x) => x?.id, ready = true, load, ...opts } = {}) {
  const dock = useDockParam(opts)
  const { item, open, close } = dock
  const held = useRef(null)
  const [loaded, setLoaded] = useState(null)
  const [, redraw] = useState(0)
  const asked = useRef(null)
  const keyRef = useRef(key)
  keyRef.current = key

  const fromList = item == null ? null : (items || []).find((x) => sameId(keyRef.current(x), item)) || null
  const fromHeld = item != null && held.current && sameId(keyRef.current(held.current), item) ? held.current : null
  const fromLoad = item != null && loaded && sameId(keyRef.current(loaded), item) ? loaded : null
  const selected = fromHeld || fromList || fromLoad

  useEffect(() => {
    if (item == null || !ready || fromList || fromHeld || fromLoad) return
    if (asked.current === item) return
    asked.current = item
    if (!load) { close(); return }
    let live = true
    Promise.resolve(load(item)).then(
      (obj) => { if (!live) return; if (obj) setLoaded(obj); else close() },
      () => { if (live) close() },
    )
    return () => { live = false }
  }, [item, ready, fromList, fromHeld, fromLoad, load, close])
  useEffect(() => { if (item == null) asked.current = null }, [item])

  const select = useCallback((obj, o) => {
    if (!obj) { held.current = null; close(); return }
    held.current = obj
    // The same object refreshed (an edit) stays where it is in the URL
    if (sameId(keyRef.current(obj), item) && !o?.section) { redraw((n) => n + 1); return }
    open(keyRef.current(obj), o)
  }, [open, close, item])

  // Holds an object whose id the caller writes into the URL itself (with another parameter, in one step)
  const hold = useCallback((obj) => { held.current = obj }, [])

  return { ...dock, selected, select, hold }
}

/**
 * A page's open id held by the URL, in place of `useState(null)`: `setOpenId(id)` opens, `setOpenId(null)` closes.
 * The id reads back as the API holds it (a number when it is one).
 */
export function useDockId(opts) {
  const dock = useDockParam(opts)
  const { open, close } = dock
  const setOpenId = useCallback((id) => (id == null ? close() : open(id)), [open, close])
  return { ...dock, openId: dock.item == null ? null : asId(dock.item), setOpenId }
}

export default useDockParam
