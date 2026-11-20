/**
 * The browser bar takes the theme's background (`--bg`): one <meta name="theme-color">,
 * created if missing, repainted whenever the theme family or mode changes on <html>.
 */
import { useEffect } from 'react'

export function paintThemeColor() {
  let meta = document.querySelector('meta[name="theme-color"]')
  if (!meta) {
    meta = document.createElement('meta')
    meta.name = 'theme-color'
    document.head.appendChild(meta)
  }
  const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()
  if (bg) meta.content = bg
}

export function useThemeColor() {
  useEffect(() => {
    paintThemeColor()
    const observer = new MutationObserver(paintThemeColor)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'data-mode'] })
    return () => observer.disconnect()
  }, [])
}
