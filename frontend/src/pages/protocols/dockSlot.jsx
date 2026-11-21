/**
 * A dock rendered by a view that holds its own state (a tab of a protocol page), at the mockup's
 * place: the Zone's dock slot (#inspector beside .page-content), through a portal that keeps the
 * Zone's anchoring context. The page wraps its Zone in <DockSlotProvider> and puts <DockSlot /> in
 * the Zone's `dock`; a view renders <SlotDock>{dock}</SlotDock>.
 */
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { DockSideContext } from '../../components/atelier/dockSide'

const SlotContext = createContext({ slot: null, setSlot: () => {} })

export function DockSlotProvider({ children }) {
  const [slot, setSlot] = useState(null)
  return <SlotContext.Provider value={{ slot, setSlot }}>{children}</SlotContext.Provider>
}

/** The slot, a box without layout of its own, in the Zone's dock subtree (it reads the anchoring setter there). */
export function DockSlot() {
  const { setSlot } = useContext(SlotContext)
  const setRight = useContext(DockSideContext)
  const ref = useRef(null)
  useEffect(() => {
    setSlot({ node: ref.current, setRight })
    return () => setSlot(null)
  }, [setRight, setSlot])
  return <div className="dock-slot" ref={ref} />
}


/** A view's dock, drawn in the slot with the Zone's anchoring context; nothing until the slot exists. */
export function SlotDock({ children }) {
  const { slot } = useContext(SlotContext)
  if (!slot?.node || !children) return null
  return createPortal(<DockSideContext.Provider value={slot.setRight}>{children}</DockSideContext.Provider>, slot.node)
}
