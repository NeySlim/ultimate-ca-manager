/**
 * DetailWindowLayer — Renders all open floating detail windows
 * 
 * Placed in App.jsx, renders FloatingDetailWindow for each entry
 * in the WindowManager context. Only active on desktop.
 */
import { FloatingDetailWindow } from './FloatingDetailWindow'
import { useWindowManager } from '../contexts/WindowManagerContext'
import { useMobile } from '../contexts/MobileContext'

export function DetailWindowLayer() {
  const { windows } = useWindowManager()
  const { isMobile } = useMobile()

  if (isMobile) return null
  if (windows.length === 0) return null

  return (
    <>
      {windows.map(win => (
        <FloatingDetailWindow key={win._tileKey ? `${win.id}-${win._tileKey}` : win.id} windowInfo={win} />
      ))}
    </>
  )
}
