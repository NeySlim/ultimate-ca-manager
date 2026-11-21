import { createContext } from 'react'

/** True under a zone (`.atl`): a dialog drawn elsewhere takes its own scope with it. */
export const AtlScopeContext = createContext(false)
