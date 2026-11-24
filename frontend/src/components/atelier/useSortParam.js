/**
 * The sort of a list, kept in the address as the mockup's Certificats (syncUrl, M:157-158): `?sort=<key>&order=asc|desc`,
 * written only when it differs from the list's default. Two states: a header not sorted sorts ascending, the
 * sorted one reverses; there is no unsorted state, and every change goes back to page one (`page` removed).
 * An unknown key falls back on the default without an error. A reload, a shared link and Back give the same order.
 */
import { useCallback, useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useLatestLocation } from './useLatestLocation'

/**
 * @param {{key: string, asc: boolean}} initial  the list's default sort: required
 * @param {string[]} keys  the sort keys the list knows
 * @param {{scope?: string}} [o]  a page that shows several lists at once (the settings) gives each its own
 *   `<scope>-sort` and `<scope>-order`; a scoped sort leaves `page` alone, which is not its own
 * @returns {{ sort: {key, asc}, onSort(key): void, setSort(next): void }}
 */
export function useSortParam(initial, keys, { scope } = {}) {
  if (!initial?.key) throw new Error('useSortParam: a list that sorts declares its default sort')
  const SORT = scope ? `${scope}-sort` : 'sort'
  const ORDER = scope ? `${scope}-order` : 'order'
  const location = useLocation()
  const navigate = useNavigate()
  // A write builds on the URL as it is now (another write in the same moment, the dock's state, the hash)
  const latest = useLatestLocation()
  const params = new URLSearchParams(location.search)
  const asked = params.get(SORT)
  const known = asked !== null && keys.includes(asked)
  const key = known ? asked : initial.key
  const asc = known ? params.get(ORDER) !== 'desc' : initial.asc !== false
  const sort = useMemo(() => ({ key, asc }), [key, asc])

  const setSort = useCallback((next) => {
    const at = latest()
    const current = new URLSearchParams(at.search)
    const was = current.get(SORT) !== null && keys.includes(current.get(SORT))
      ? { key: current.get(SORT), asc: current.get(ORDER) !== 'desc' } : { key: initial.key, asc: initial.asc !== false }
    const s = typeof next === 'function' ? next(was) : next
    const plain = s.key === initial.key && s.asc === (initial.asc !== false)
    current.delete(SORT)
    current.delete(ORDER)
    if (!scope) current.delete('page')
    if (!plain) { current.set(SORT, s.key); current.set(ORDER, s.asc ? 'asc' : 'desc') }
    const qs = current.toString()
    navigate({ pathname: at.pathname, search: qs ? `?${qs}` : '', hash: at.hash }, { replace: true, state: at.state })
  }, [navigate, latest, initial.key, initial.asc, keys.join(','), SORT, ORDER]) // eslint-disable-line react-hooks/exhaustive-deps

  const onSort = useCallback((k) => setSort((s) => ({ key: k, asc: s.key === k ? !s.asc : true })), [setSort])
  return { sort, onSort, setSort }
}

export default useSortParam
