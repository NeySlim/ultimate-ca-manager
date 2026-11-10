/**
 * StatusFooter — Fixed footer bar for the inspector
 * 
 * Left: open object count and close all
 * Right: option (close on navigate)
 * Hidden on dashboard and mobile.
 */
import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { X, SquaresFour } from '@phosphor-icons/react'
import { useInspector } from '../../contexts/InspectorContext'
import { cn } from '../../lib/utils'

// A detail URL (/certificates/12) belongs to its list page: opening one is no page change
const pageOf = (pathname) => pathname.replace(/\/\d+\/?$/, '') || '/'

export function StatusFooter() {
  const { t } = useTranslation()
  const location = useLocation()
  const page = pageOf(location.pathname)
  const prevPage = useRef(page)
  const { openCount: windowCount, closeAll, closeOnNav, toggleCloseOnNav } = useInspector()

  // Close windows on navigation if option enabled
  useEffect(() => {
    if (closeOnNav && prevPage.current !== page && windowCount > 0) {
      closeAll()
    }
    prevPage.current = page
  }, [page, closeOnNav, closeAll, windowCount])

  return (
    <div className={cn(
      'shrink-0 h-8 flex items-center justify-between',
      'px-3 border-t border-border-op50 bg-secondary-op40',
      'text-xs select-none',
    )}>
      {/* Left: Window controls */}
      <div className="flex items-center gap-1">
        {windowCount > 0 ? (
          <>
            {/* Window count badge */}
            <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-accent-primary-op10 mr-0.5">
              <SquaresFour size={12} weight="duotone" className="text-accent-primary" />
              <span className="text-xs font-semibold text-accent-primary">{windowCount}</span>
            </div>

            <button
              onClick={() => closeAll()}
              data-inspector-control
              className="h-6 px-1.5 rounded flex items-center gap-1 text-text-secondary hover:text-status-danger hover:bg-status-danger-op10 transition-colors"
              title={t('windows.closeAll', 'Close All')}
            >
              <X size={13} weight="bold" />
            </button>
          </>
        ) : (
          <span className="text-xs text-text-tertiary">{t('windows.noWindows', 'No windows open')}</span>
        )}
      </div>

      {/* Right: Options */}
      <div className="flex items-center gap-3">
        {/* Close on navigate toggle */}
        <label className="flex items-center gap-1.5 cursor-pointer group">
          <input
            type="checkbox"
            checked={closeOnNav}
            onChange={toggleCloseOnNav}
            className="w-3 h-3 rounded border-border accent-accent-primary cursor-pointer"
          />
          <span className="text-xs text-text-tertiary group-hover:text-text-secondary transition-colors">
            {t('windows.closeOnNav', 'Close on navigate')}
          </span>
        </label>
      </div>
    </div>
  )
}
