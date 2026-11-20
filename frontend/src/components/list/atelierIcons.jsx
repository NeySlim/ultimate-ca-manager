/**
 * Pictograms of the Atelier mockup that the icon set draws differently (columns,
 * rows, one circular arrow, the corners of Agrandir): same 24-unit paths, stroke 1.6.
 */
const PATHS = {
  columns: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16m6-16v16" /></>,
  rows: <path d="M4 5h16M4 10h16M4 15h16M4 20h16" />,
  refresh: <path d="M20 8A8 8 0 1 0 20 16M20 3v5h-5" />,
  expand: <path d="M8 3H3v5m13-5h5v5M3 16v5h5m8 0h5v-5" />,
  filter: <path d="M3 5h18l-7 8v7l-4-2v-5L3 5Z" />,
}

function make(name) {
  function AtelierIcon({ size = 17, className, ...props }) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" className={className} {...props}>
        {PATHS[name]}
      </svg>
    )
  }
  AtelierIcon.displayName = `AtelierIcon(${name})`
  return AtelierIcon
}

export const ColumnsIcon = make('columns')
export const RowsIcon = make('rows')
export const RefreshIcon = make('refresh')
export const ExpandIcon = make('expand')
export const FilterIcon = make('filter')
