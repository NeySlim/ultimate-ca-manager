import { useSyncExternalStore } from 'react'

/** The width the stylesheets switch to the phone layout at (`@media (max-width: 800px)`). */
export const PHONE_WIDTH = '(max-width: 800px)'

const list = (query) => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query) : null)

/** Whether `query` matches, read again each time the browser says it changed (a resize across it). */
export function useMediaQuery(query) {
  return useSyncExternalStore(
    (notify) => {
      const media = list(query)
      if (!media) return () => {}
      if (media.addEventListener) {
        media.addEventListener('change', notify)
        return () => media.removeEventListener('change', notify)
      }
      media.addListener?.(notify)
      return () => media.removeListener?.(notify)
    },
    () => !!list(query)?.matches,
    () => false,
  )
}

/** True while the window is as narrow as the stylesheets' phone layout. */
export const usePhoneWidth = () => useMediaQuery(PHONE_WIDTH)
