/**
 * Pagination Component
 */
import { CaretLeft, CaretRight, CaretDoubleLeft, CaretDoubleRight } from '@phosphor-icons/react'
import { Button } from './Button'
import { cn } from '../lib/utils'
import { FilterSelect } from './ui/Select'

const PAGE_SIZE_OPTIONS = [
  { value: '10', label: '10' },
  { value: '20', label: '20' },
  { value: '50', label: '50' },
  { value: '100', label: '100' },
]

export function Pagination({ 
  total = 0, 
  page = 1, 
  perPage = 20, 
  onChange,
  onPerPageChange,
  showInfo = true,
  showPerPageSelector = true
}) {
  const totalPages = Math.max(1, Math.ceil(total / perPage) || 1)
  const start = total > 0 ? (page - 1) * perPage + 1 : 0
  const end = Math.min(page * perPage, total)

  return (
    <div className="flex items-center justify-between px-4 py-2.5 text-sm">
      {showInfo && (
        <div className="text-text-secondary text-xs">
          <span className="font-medium text-text-primary">{start}</span>-
          <span className="font-medium text-text-primary">{end}</span> of{' '}
          <span className="font-medium text-text-primary">{total}</span>
        </div>
      )}

      <div className="flex items-center gap-3 ml-auto">
        {showPerPageSelector && onPerPageChange && (
          <div className="flex items-center gap-1.5">
            <span className="text-text-tertiary text-xs">Rows:</span>
            <FilterSelect
              value={String(perPage)}
              onChange={(val) => onPerPageChange(Number(val))}
              options={PAGE_SIZE_OPTIONS}
              placeholder={String(perPage)}
              size="sm"
            />
          </div>
        )}

        <div className="flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onChange(1)}
            disabled={page === 1}
            className="px-1.5 py-1"
          >
            <CaretDoubleLeft size={14} />
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => onChange(page - 1)}
            disabled={page === 1}
            className="px-1.5 py-1"
          >
            <CaretLeft size={14} />
          </Button>

          <div className="flex items-center gap-0.5 mx-1">
            {[...Array(Math.min(totalPages, 5))].map((_, i) => {
              let pageNum
              if (totalPages <= 5) {
                pageNum = i + 1
              } else if (page <= 3) {
                pageNum = i + 1
              } else if (page >= totalPages - 2) {
                pageNum = totalPages - 4 + i
              } else {
                pageNum = page - 2 + i
              }

              return (
                <button
                  key={pageNum}
                  onClick={() => onChange(pageNum)}
                  className={cn(
                    "min-w-[28px] h-7 rounded text-xs font-medium transition-all",
                    page === pageNum
                      ? "bg-accent-primary text-white"
                      : "text-text-secondary bg-tertiary-op50 hover:bg-bg-tertiary hover:text-text-primary"
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
            className="px-1.5 py-1"
          >
            <CaretRight size={14} />
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => onChange(totalPages)}
            disabled={page === totalPages}
            className="px-1.5 py-1"
          >
            <CaretDoubleRight size={14} />
          </Button>
        </div>
      </div>
    </div>
  )
}
