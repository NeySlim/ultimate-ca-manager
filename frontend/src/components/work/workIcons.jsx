/**
 * Pictograms of the Atelier mockup that the queue pages draw and the icon set draws
 * differently (simple check, clock at 4 o'clock, chart, policy scales): 24-unit paths, stroke 1.6.
 */
const PATHS = {
  check: <path d="m5 12 4 4L19 6" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  chart: <><path d="M4 4v16h16" /><path d="M8 16v-4m4 4V8m4 8v-6" /></>,
  policy: <path d="M12 3v18M7 21h10M5 7h14M5 7l-3 7a3 3 0 0 0 6 0L5 7Zm14 0-3 7a3 3 0 0 0 6 0l-3-7Z" />,
}

function make(name) {
  function WorkIcon({ size = 17, className, ...props }) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" className={className} {...props}>
        {PATHS[name]}
      </svg>
    )
  }
  WorkIcon.displayName = `WorkIcon(${name})`
  return WorkIcon
}

export const CheckIcon = make('check')
export const ClockIcon = make('clock')
export const ChartIcon = make('chart')
export const PolicyIcon = make('policy')
