/**
 * Sort and pages of a module list whose API sends every row: the conduct of the mockup's
 * Certificats list (a header sorts, a second click reverses, back to page one; M:167-168, M:1419)
 * applied in memory. A list the server pages keeps its own state and passes sort and pagination itself.
 */
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

export const PAGE_SIZES = [10, 25, 50, 100]

const blank = (v) => v === null || v === undefined || v === '' || (typeof v === 'number' && Number.isNaN(v))

/** Empty values sort last whichever the direction: a missing date is no earlier than any date. */
export function compareValues(a, b, asc, collator) {
  if (blank(a) || blank(b)) return blank(a) === blank(b) ? 0 : blank(a) ? 1 : -1
  let order
  if (typeof a === 'number' && typeof b === 'number') order = a === b ? 0 : a < b ? -1 : 1
  else order = collator.compare(String(a), String(b))
  return asc ? order : -order
}

/**
 * @param {Array} rows  the rows after the search and the state chips
 * @param {object} o
 * @param {Record<string, (row) => any>} o.sorts  each sortable column's key and the value it sorts by
 * @param {{key, asc}|null} [o.initial]  null keeps the API's order until a header is clicked
 * @param {number} [o.perPage]
 * @param {string} [o.resetKey]  the filters: a change goes back to page one
 * @returns {{ rows, sort, onSort, total, start, end, paged, pagination, counts }}  pagination only past the smallest page size
 */
export function useClientList(rows, { sorts = {}, initial = null, perPage: firstPerPage = 25, sizes = PAGE_SIZES, resetKey = '' } = {}) {
  const { i18n } = useTranslation()
  const [sort, setSort] = useState(initial)
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(firstPerPage)
  const [mark, setMark] = useState(resetKey)
  if (mark !== resetKey) { setMark(resetKey); setPage(1) }

  const language = i18n?.language
  const sorted = useMemo(() => {
    const value = sort && sorts[sort.key]
    if (!value) return rows
    const collator = new Intl.Collator(language || undefined, { numeric: true, sensitivity: 'base' })
    // Array.prototype.sort is stable: equal values keep the API's order
    return [...rows].sort((a, b) => compareValues(value(a), value(b), sort.asc, collator))
  }, [rows, sort, language]) // eslint-disable-line react-hooks/exhaustive-deps

  const total = sorted.length
  const pages = Math.max(1, Math.ceil(total / perPage))
  const current = Math.min(page, pages)
  const paged = total > Math.min(...sizes)
  const shown = paged ? sorted.slice((current - 1) * perPage, current * perPage) : sorted
  return {
    rows: shown,
    sort,
    onSort: (key) => { setSort((s) => ({ key, asc: s?.key === key ? !s.asc : true })); setPage(1) },
    total,
    start: total ? (paged ? (current - 1) * perPage + 1 : 1) : 0,
    end: paged ? Math.min(current * perPage, total) : total,
    paged,
    // The arguments of a module's « {{shown}} of {{count}} » range: « 1–25 of 30 » once paged, « 12 of 139 » before
    counts: (all) => (paged ? { shown: `${(current - 1) * perPage + 1}–${Math.min(current * perPage, total)}`, count: total } : { shown: total, count: all ?? total }),
    pagination: paged ? {
      page: current, pages, perPage, sizes,
      onPage: setPage,
      onPerPage: (n) => { setPerPage(n); setPage(1) },
    } : undefined,
  }
}

export default useClientList
