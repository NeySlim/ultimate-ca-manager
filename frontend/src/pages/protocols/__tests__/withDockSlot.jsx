/** Test harness: a view that draws its dock in the page's slot, rendered with a slot as the page gives it. */
import { DockSlot, DockSlotProvider } from '../dockSlot'

export function WithDockSlot({ children }) {
  return <DockSlotProvider><div className="atl">{children}<DockSlot /></div></DockSlotProvider>
}
