import { createContext, useContext, useState } from 'react'

/** Set by the Zone: the dock tells it when it is anchored at the right (#app.dock-right). */
export const DockSideContext = createContext(null)

// The narrowest window that offers the right anchoring: 1200 px by the maintainer's choice (the
// mockup's dockSide() says 1400). The CSS keys on #app.dock-right, set from this one value.
export const DOCK_RIGHT_MIN = 1200

// The defaults of the Atelier layout: a 278 px band under the list, a 460 px column beside it
export const DOCK_DEFAULTS = { position: 'bottom', height: 278, width: 460 }

/** The one dock preference of the user (position, height, width, fold), held by InspectorProvider. */
export const DockPreferenceContext = createContext(null)

/** The user's dock preference; outside an InspectorProvider (an isolated render), a state of its own. */
export function useDockPreference() {
  const held = useContext(DockPreferenceContext)
  const [own, setOwn] = useState(DOCK_DEFAULTS)
  const [ownCollapsed, setOwnCollapsed] = useState(false)
  if (held) return held
  return { ...own, setGeometry: (patch) => setOwn((cur) => ({ ...cur, ...patch })), collapsed: ownCollapsed, setCollapsed: setOwnCollapsed }
}
