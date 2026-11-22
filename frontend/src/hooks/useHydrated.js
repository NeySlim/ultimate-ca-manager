import { useSyncExternalStore } from 'react'

const subscribe = () => () => {}

/**
 * False while the server draws a page and while React takes that drawing over, true otherwise:
 * what depends on the account (its rights) is left out of the first render the server shares.
 */
export const useHydrated = () => useSyncExternalStore(subscribe, () => true, () => false)
