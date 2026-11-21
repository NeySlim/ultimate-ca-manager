/**
 * The object a dock shows and its section, kept in the URL as the mockup keeps them (`item`, its
 * inspector `tab`, M:134-161): `?item=<id>&section=<id>`. `tab` already names the sub-view of
 * several pages, so the section takes `section`. Opening adds a history step, so Back closes the
 * dock; a section change or another object replaces it; closing a dock opened here steps back.
 * A dock with several open objects (`list`) also keeps them, as the mockup's `open=1,2,3`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'

export const ITEM_PARAM = 'item'
export const SECTION_PARAM = 'section'
export const LIST_PARAM = 'open'
const NONE = []
// The mark of a history step this hook added: closing then steps back instead of adding one
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
  const location = useLocation()
  const navigate = useNavigate()
  const names = [ITEM_PARAM, ...aliases]
  const item = names.map((n) => params.get(n)).find((v) => v) ?? null
  const raw = params.get(SECTION_PARAM)
  const section = item && raw && (!sections || sections.includes(raw)) ? raw : fallback
  const listRaw = withList ? params.get(LIST_PARAM) : null
  const list = useMemo(() => (listRaw ? [...new Set(listRaw.split(',').filter(Boolean))] : NONE), [listRaw])

  // The latest URL, so callbacks stay stable while writing on top of it
  const now = useRef(null)
  now.current = { params, location, item }
  const aliasKey = aliases.join(',')

  const write = useCallback((patch, { push = false } = {}) => {
    const { params: cur, location: loc } = now.current
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
    const state = push ? { ...(loc.state || {}), [OPENED]: true } : loc.state
    navigate(to, { replace: !push, state })
    // A second write in the same handler builds on this one, not on the URL still rendered
    now.current = { params: next, location: { ...loc, search: to.search, state }, item: patch.item != null ? String(patch.item) : null }
  }, [navigate, fallback, aliasKey, withList])

  const open = useCallback((id, { section: asked, list: ids } = {}) => {
    if (id == null) return
    const cur = now.current.item
    const keep = sameId(cur, id) && !asked ? now.current.params.get(SECTION_PARAM) : asked
    write({ item: id, section: keep, list: ids }, { push: cur == null })
  }, [write])

  const close = useCallback(() => {
    const { item: cur, location: loc } = now.current
    if (cur == null) return
    if (loc.state?.[OPENED] && loc.key !== 'default') {
      navigate(-1)
      now.current = { ...now.current, item: null }
    } else write({})
  }, [navigate, write])

  const setSection = useCallback((id) => {
    const cur = now.current.item
    if (cur != null) write({ item: cur, section: id })
  }, [write])

  // The open objects changed, the shown one did not
  const setList = useCallback((ids) => {
    const cur = now.current.item
    if (cur != null) write({ item: cur, section: now.current.params.get(SECTION_PARAM), list: ids })
  }, [write])

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
