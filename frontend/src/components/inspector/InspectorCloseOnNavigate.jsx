/** Closes the inspector objects when the operator changes page, while the "close on navigate" preference is on. */
import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { useInspector } from '../../contexts/InspectorContext'
// A detail URL (/certificates/12) belongs to its list page: opening one is no page change
import { pageOf } from '../../lib/pageOf'

export function InspectorCloseOnNavigate() {
  const page = pageOf(useLocation().pathname)
  const prevPage = useRef(page)
  const { openCount, closeAll, closeOnNav } = useInspector()

  useEffect(() => {
    if (closeOnNav && prevPage.current !== page && openCount > 0) closeAll()
    prevPage.current = page
  }, [page, closeOnNav, closeAll, openCount])

  return null
}
