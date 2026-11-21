/**
 * The state banners' place: the mockup draws them at the top of the page content. A zone drawn
 * from the mockup (atelier/Zone) shows them there and claims them; the shell shows them above
 * any other page.
 */
import { createContext, useContext, useLayoutEffect } from 'react'

export const ShellBannersContext = createContext(null)

/** In a zone's page content: the banners, the shell's own place left empty while it is mounted. */
export function useShellBanners() {
  const shell = useContext(ShellBannersContext)
  const claim = shell?.claim
  useLayoutEffect(() => claim?.(), [claim])
  return shell?.node ?? null
}
