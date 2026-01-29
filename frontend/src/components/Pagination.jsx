/**
 * Pagination Component
 */
import { CaretLeft, CaretRight, CaretDoubleLeft, CaretDoubleRight } from '@phosphor-icons/react'
import { Button } from './Button'
import { cn } from '../lib/utils'

export function Pagination({ 
  total = 0, 
  page = 1, 
  perPage = 20, 
  onChange,
  showInfo = true 
}) {
  const totalPages = Math.max(1, Math.ceil(total / perPage) || 1)
  const start = total > 0 ? (page - 1) * perPage + 1 : 0
  const end = Math.min(page * perPage, total)

  return (
    <div className="flex items-center justify-between px-4 py-3 text-sm">
      {showInfo && (
        <div className="text-text-secondary">
          Showing <span className="font-medium text-text-primary">{start}</span> to{' '}
          <span className="font-medium text-text-primary">{end}</span> of{' '}
          <span className="font-medium text-text-primary">{total}</span> results
        </div>
      )}

      <div className="flex items-center gap-2 ml-auto">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onChange(1)}
          disabled={page === 1}
          className="px-2"
        >
          <CaretDoubleLeft size={16} />
        </Button>

        <Button
          variant="ghost"
          size="sm"
          onClick={() => onChange(page - 1)}
          disabled={page === 1}
          className="px-2"
        >
          <CaretLeft size={16} />
        </Button>

        <div className="flex items-center gap-1">
          {[...Array(totalPages)].map((_, i) => {
            const pageNum = i + 1
            const showPage = 
              pageNum === 1 ||
              pageNum === totalPages ||
              (pageNum >= page - 1 && pageNum <= page + 1)

            if (!showPage && pageNum === page - 2) {
              return <span key={pageNum} className="px-2 text-text-secondary">...</span>
            }
            if (!showPage && pageNum === page + 2) {
              return <span key={pageNum} className="px-2 text-text-secondary">...</span>
            }
            if (!showPage) return null

            return (
              <button
                key={pageNum}
                onClick={() => onChange(pageNum)}
                className={cn(
                  "w-8 h-8 rounded-lg text-sm font-medium transition-colors",
                  page === pageNum
                    ? "bg-accent-primary text-white"
                    : "text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
                )}
              >
                {pageNum}
              </button>
            )
          })}
        </div>

        <Button
          variant="ghost"
          size="sm"
          onClick={() => onChange(page + 1)}
          disabled={page === totalPages}
          className="px-2"
        >
          <CaretRight size={16} />
        </Button>

        <Button
          variant="ghost"
          size="sm"
          onClick={() => onChange(totalPages)}
          disabled={page === totalPages}
          className="px-2"
        >
          <CaretDoubleRight size={16} />
        </Button>
      </div>
    </div>
  )
}
