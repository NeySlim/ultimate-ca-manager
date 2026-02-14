/**
 * StatusFooter — Fixed footer bar for window management & options
 * 
 * Left: window controls (count badge, tile, cascade, close all)
 * Right: options (same window, close on navigate)
 * Hidden on dashboard and mobile.
 */
import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  X, GridFour, Stack, SquaresFour,
  ArrowsInLineHorizontal, NavigationArrow,
} from '@phosphor-icons/react'
import { useWindowManager } from '../../contexts/WindowManagerContext'
import { cn } from '../../lib/utils'

export function StatusFooter() {
  const { t } = useTranslation()
  const location = useLocation()
  const prevPath = useRef(location.pathname)
  const {
    windowCount, closeAll, tileWindows, stackWindows,
    sameWindow, closeOnNav, toggleSameWindow, toggleCloseOnNav,
  } = useWindowManager()

  // Close windows on navigation if option enabled
  useEffect(() => {
    if (closeOnNav && prevPath.current !== location.pathname && windowCount > 0) {
      closeAll()
    }
    prevPath.current = location.pathname
  }, [location.pathname, closeOnNav, closeAll, windowCount])

  return (
    <div className={cn(
      'shrink-0 h-8 flex items-center justify-between',
      'px-3 border-t border-border/50 bg-bg-secondary/40',
      'text-xs select-none',
    )}>
      {/* Left: Window controls */}
      <div className="flex items-center gap-1">
        {windowCount > 0 ? (
          <>
            {/* Window count badge */}
            <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-accent-primary/10 mr-0.5">
              <SquaresFour size={12} weight="duotone" className="text-accent-primary" />
              <span className="text-[11px] font-semibold text-accent-primary">{windowCount}</span>
            </div>

            <button
              onClick={tileWindows}
              className="h-6 px-1.5 rounded flex items-center gap-1 text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
              title={t('windows.tile', 'Tile')}
            >
              <GridFour size={13} weight="duotone" />
            </button>

            <button
              onClick={stackWindows}
              className="h-6 px-1.5 rounded flex items-center gap-1 text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
              title={t('windows.stack', 'Cascade')}
            >
              <Stack size={13} weight="duotone" />
            </button>

            <button
              onClick={closeAll}
              className="h-6 px-1.5 rounded flex items-center gap-1 text-text-secondary hover:text-status-danger hover:bg-status-danger/10 transition-colors"
              title={t('windows.closeAll', 'Close All')}
            >
              <X size={13} weight="bold" />
            </button>
          </>
        ) : (
          <span className="text-[11px] text-text-tertiary">{t('windows.noWindows', 'No windows open')}</span>
        )}
      </div>

      {/* Right: Options */}
      <div className="flex items-center gap-3">
        {/* Same window toggle */}
        <label className="flex items-center gap-1.5 cursor-pointer group">
          <input
            type="checkbox"
            checked={sameWindow}
            onChange={toggleSameWindow}
            className="w-3 h-3 rounded border-border accent-accent-primary cursor-pointer"
          />
          <span className="text-[11px] text-text-tertiary group-hover:text-text-secondary transition-colors">
            {t('windows.sameWindow', 'Same window')}
          </span>
        </label>

        {/* Close on navigate toggle */}
        <label className="flex items-center gap-1.5 cursor-pointer group">
          <input
            type="checkbox"
            checked={closeOnNav}
            onChange={toggleCloseOnNav}
            className="w-3 h-3 rounded border-border accent-accent-primary cursor-pointer"
          />
          <span className="text-[11px] text-text-tertiary group-hover:text-text-secondary transition-colors">
            {t('windows.closeOnNav', 'Close on navigate')}
          </span>
        </label>
      </div>
    </div>
  )
}
