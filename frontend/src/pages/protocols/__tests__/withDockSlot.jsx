/** Test harness: a view that draws its dock in the page's slot, rendered with a slot as the page gives it, in a router (the dock's object lives in the URL). */
import { MemoryRouter, useInRouterContext } from 'react-router-dom'
import { DockSlot, DockSlotProvider } from '../dockSlot'

export function WithDockSlot({ children }) {
  const routed = useInRouterContext()
  const ui = <DockSlotProvider><div className="atl">{children}<DockSlot /></div></DockSlotProvider>
  return routed ? ui : <MemoryRouter>{ui}</MemoryRouter>
}
