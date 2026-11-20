/**
 * Save parts of a sectioned form. Each part is one route of today's API with its own
 * draft: { section, dirty, count, save, reset }. `save` resolves true once stored.
 * Parts kept inside a section (its own state) register through the context.
 */
import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { keepDraft, readDraft } from './draftMemory'

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

/**
 * Registers a part held by a section; the latest closures are kept at each render.
 * A part that gives its `draft` (once loaded) has it kept for the tab while it counts changes.
 */
export function useSavePart(key, part) {
  const api = useContext(SavePartsContext)
  useEffect(() => {
    api?.set(key, part)
    if (part.draft !== undefined) keepDraft(partDraftKey(key), part.count > 0 ? part.draft : null)
  })
  useEffect(() => () => api?.remove(key), [api, key])
}

const partDraftKey = (key) => `part:${key}`

/** The draft a section part left pending, read once when the section loads. */
export function keptPartDraft(key) {
  return readDraft(partDraftKey(key))
}

/** Count of the changes in a draft against what was loaded, key by key. */
export function changedKeys(draft, saved, keys) {
  const norm = (v) => (v === undefined || v === null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v))
  return keys.filter((k) => norm(draft?.[k]) !== norm(saved?.[k]))
}

/**
 * While `active`, a reload or a close of the tab asks the browser first; moving to another
 * page needs no question, the draft is kept for the return (`draftMemory`).
 */
export function useUnloadGuard(active) {
  useEffect(() => {
    if (!active) return undefined
    const onBeforeUnload = (e) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [active])
}
