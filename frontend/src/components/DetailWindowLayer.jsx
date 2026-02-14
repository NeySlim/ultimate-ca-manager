/**
 * DetailWindowLayer — Renders all open floating detail windows
 * 
 * Placed in App.jsx, renders FloatingDetailWindow for each entry
 * in the WindowManager context. Only active on desktop.
 */
import { FloatingDetailWindow } from './FloatingDetailWindow'
import { WindowToolbar } from './ui/WindowToolbar'
import { useWindowManager } from '../contexts/WindowManagerContext'
import { useMobile } from '../contexts/MobileContext'

export function DetailWindowLayer() {
  const { windows } = useWindowManager()
  const { isMobile } = useMobile()

  // Don't render floating windows on mobile/tablet
  if (isMobile) return null
  if (windows.length === 0) return null

  return (
    <>
      {windows.map(win => (
        <FloatingDetailWindow key={win.id} windowInfo={win} />
      ))}
      <WindowToolbar />
    </>
  )
}
