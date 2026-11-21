/**
 * Renders a page at a URL and reads the URL it writes: the dock's object and section live there.
 */
import { render, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

export function renderAtUrl(ui, url) {
  const seen = { url }
  function Where() { const l = useLocation(); seen.url = l.pathname + l.search; return null }
  const r = render(<MemoryRouter initialEntries={[url]}>{ui}<Where /></MemoryRouter>)
  const dock = () => waitFor(() => {
    const d = r.container.querySelector('aside#inspector, #inspector')
    if (!d) throw new Error('no dock')
    return d
  })
  return { ...r, where: () => seen.url, dock }
}
