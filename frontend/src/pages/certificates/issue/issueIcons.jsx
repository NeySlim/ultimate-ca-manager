/**
 * The pictograms of the Atelier's issue dialog, drawn as its icons are: 24-unit paths, stroke 1.6.
 * The dialog's rules size them (17 px in buttons and steps, 16 in icon buttons, 13 or 14 in notes).
 */
const PATHS = {
  close: <path d="m6 6 12 12M6 18 18 6" />,
  right: <path d="m9 5 7 7-7 7" />,
  left: <path d="m15 5-7 7 7 7" />,
  down: <path d="m5 9 7 7 7-7" />,
  check: <path d="m5 12 4 4L19 6" />,
  plus: <path d="M12 4v16M4 12h16" />,
  help: <><circle cx="12" cy="12" r="9" /><path d="M9 8a3 3 0 0 1 6 1c0 2-3 2-3 4m0 3v1" /></>,
  warning: <><path d="M12 3 2 21h20L12 3Z" /><path d="M12 9v5m0 3v1" /></>,
}

function make(name) {
  function IssueIcon({ className, ...props }) {
    return (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" className={className} {...props}>
        {PATHS[name]}
      </svg>
    )
  }
  IssueIcon.displayName = `IssueIcon(${name})`
  return IssueIcon
}

export const X = make('close')
export const CaretRight = make('right')
export const CaretLeft = make('left')
export const CaretDown = make('down')
export const Check = make('check')
export const Plus = make('plus')
export const Question = make('help')
export const Warning = make('warning')
