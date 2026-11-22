import { createContext, useContext } from 'react'

/** Held by DetachedProvider (the shell). */
export const DetachedContext = createContext(null)

/** The detached windows, or null outside the shell (an isolated page): no Detach button then. */
export const useDetached = () => useContext(DetachedContext)

export const windowKey = (kind, ids) => `${kind}:${[].concat(ids).map(String).join(',')}`
