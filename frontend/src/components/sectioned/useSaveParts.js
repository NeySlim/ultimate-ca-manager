/**
 * Save parts of a sectioned form. Each part is one route of today's API with its own
 * draft: { section, dirty, count, save, reset }. `save` resolves true once stored.
 * Parts kept inside a section (its own state) register through the context.
 */
import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { setLeaveGuard } from '../../navigation/leaveGuard'

export const SavePartsContext = createContext(null)

export function useSavePartsRegistry() {
  const parts = useRef(new Map())
  const [version, setVersion] = useState(0)
  const api = useMemo(() => ({
    set(key, part) {
      const prev = parts.current.get(key)
      parts.current.set(key, part)
      if (!prev || prev.dirty !== part.dirty || prev.count !== part.count) setVersion((v) => v + 1)
    },
    remove(key) {
      if (parts.current.delete(key)) setVersion((v) => v + 1)
    },
  }), [])
  const list = useMemo(() => [...parts.current.values()], [version]) // eslint-disable-line react-hooks/exhaustive-deps
  return { api, list }
}

/** Registers a part held by a section; the latest closures are kept at each render. */
export function useSavePart(key, part) {
  const api = useContext(SavePartsContext)
  useEffect(() => { api?.set(key, part) })
  useEffect(() => () => api?.remove(key), [api, key])
}

/** Count of the changes in a draft against what was loaded, key by key. */
export function changedKeys(draft, saved, keys) {
  const norm = (v) => (v === undefined || v === null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v))
  return keys.filter((k) => norm(draft?.[k]) !== norm(saved?.[k]))
}

/**
 * While `active`, leaving the page asks first: a link to another page, a reload or a close
 * of the tab, and the palette or any caller of `whenLeaving`.
 */
export function useLeaveGuard(active, ask) {
  const navigate = useNavigate()
  const askRef = useRef(ask)
  askRef.current = ask
  useEffect(() => {
    if (!active) return undefined
    const onBeforeUnload = (e) => {
      e.preventDefault()
      e.returnValue = ''
    }
    const onClick = (e) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      const link = e.target.closest?.('a[href]')
      if (!link || link.target === '_blank' || link.hasAttribute('download')) return
      const url = new URL(link.href, window.location.href)
      if (url.origin !== window.location.origin || url.pathname === window.location.pathname) return
      e.preventDefault()
      e.stopPropagation()
      Promise.resolve(askRef.current()).then((ok) => {
        if (ok) navigate(url.pathname + url.search + url.hash)
      })
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    document.addEventListener('click', onClick, true)
    const release = setLeaveGuard(() => askRef.current())
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload)
      document.removeEventListener('click', onClick, true)
      release()
    }
  }, [active, navigate])
}
