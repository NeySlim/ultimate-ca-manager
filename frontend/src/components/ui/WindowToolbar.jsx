/**
 * WindowToolbar — Floating toolbar for managing detail windows
 * 
 * Fixed bottom-right, only visible when windows are open.
 * Actions: Close All, Tile, Stack, window count badge.
 */
import { X, GridFour, SquaresFour, Stack } from '@phosphor-icons/react'
import { useWindowManager } from '../../contexts/WindowManagerContext'
import { useTranslation } from 'react-i18next'
import { cn } from '../../lib/utils'

export function WindowToolbar() {
  const { t } = useTranslation()
  const { windowCount, closeAll, tileWindows, stackWindows } = useWindowManager()

  if (windowCount === 0) return null

  return (
    <div className={cn(
      'fixed bottom-4 right-4 z-[200]',
      'flex items-center gap-1 px-2 py-1.5',
      'bg-bg-primary/95 backdrop-blur-sm border border-border rounded-xl',
      'shadow-lg',
    )}>
      {/* Window count badge */}
      <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-accent-primary/10 mr-1">
        <SquaresFour size={14} weight="duotone" className="text-accent-primary" />
        <span className="text-xs font-semibold text-accent-primary">{windowCount}</span>
      </div>

      {/* Tile */}
      <button
        onClick={tileWindows}
        className="w-8 h-8 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
        title={t('windows.tile', 'Tile')}
      >
        <GridFour size={16} weight="duotone" />
      </button>

      {/* Stack / Cascade */}
      <button
        onClick={stackWindows}
        className="w-8 h-8 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
        title={t('windows.stack', 'Stack')}
      >
        <Stack size={16} weight="duotone" />
      </button>

      {/* Close All */}
      <button
        onClick={closeAll}
        className="w-8 h-8 rounded-lg flex items-center justify-center text-text-secondary hover:text-status-danger hover:bg-status-danger/10 transition-colors"
        title={t('windows.closeAll', 'Close All')}
      >
        <X size={16} weight="bold" />
      </button>
    </div>
  )
}
