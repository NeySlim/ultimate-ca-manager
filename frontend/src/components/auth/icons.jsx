/**
 * The design's own strokes for the sign-in frame (its icons.js: 24 px grid, 1.6 stroke),
 * where Phosphor draws them otherwise: chevron, padlock, two offset busts.
 */
function Stroke({ size = 17, children }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  )
}

export function ChevronIcon(props) {
  return <Stroke {...props}><path d="m9 5 7 7-7 7" /></Stroke>
}

export function LockIcon(props) {
  return (
    <Stroke {...props}>
      <rect x="5" y="10" width="14" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" />
    </Stroke>
  )
}

export function SsoIcon(props) {
  return (
    <Stroke {...props}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M3 20a6 6 0 0 1 12 0M16 4.5a3.5 3.5 0 0 1 0 7m2 2.5a6 6 0 0 1 3 6" />
    </Stroke>
  )
}
