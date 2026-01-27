/**
 * Loading Spinner Component
 */
import { cn } from '../lib/utils'

export function LoadingSpinner({ size = 'md', fullscreen = false, message }) {
  const sizes = {
    sm: 'w-4 h-4 border-2',
    md: 'w-8 h-8 border-2',
    lg: 'w-12 h-12 border-3',
  }

  const spinner = (
    <div className="flex flex-col items-center gap-3">
      <div className={cn(
        "animate-spin rounded-full border-accent-primary border-t-transparent",
        sizes[size]
      )} />
      {message && (
        <p className="text-sm text-text-secondary">{message}</p>
      )}
    </div>
  )

  if (fullscreen) {
    return (
      <div className="fixed inset-0 bg-bg-primary/80 backdrop-blur-sm flex items-center justify-center z-50">
        {spinner}
      </div>
    )
  }

  return spinner
}
