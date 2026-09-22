// Walk a listing that pages on page/per_page, up to `max` rows.
export async function fetchAllPages(getPage, { perPage = 100, max = 500 } = {}) {
  const query = { per_page: perPage }
  const first = await getPage({ ...query, page: 1 })
  let rows = first.data || []
  const total = Math.min(first.meta?.total ?? rows.length, max)
  const pages = Math.ceil(total / perPage)
  if (pages > 1) {
    const rest = await Promise.all(
      Array.from({ length: pages - 1 }, (_, k) => getPage({ ...query, page: k + 2 }))
    )
    rows = rest.reduce((acc, r) => acc.concat(r.data || []), rows)
  }
  return rows
}
