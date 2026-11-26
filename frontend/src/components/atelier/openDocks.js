import { useEffect, useSyncExternalStore } from 'react'

// How many docks (inspectors) are mounted: the status bar names Escape only while one is
let count = 0
const listeners = new Set()
const emit = () => { for (const l of listeners) l() }
const subscribe = (l) => { listeners.add(l); return () => listeners.delete(l) }

/** Counts the calling dock as open while it is mounted. */
export function useDockMounted() {
  useEffect(() => {
    count += 1
    emit()
    return () => { count -= 1; emit() }
  }, [])
}

export const useAnyDockOpen = () => useSyncExternalStore(subscribe, () => count > 0, () => false)
