// A toast opened over a dialog is Radix's highest layer and takes Escape from it: the toast
// yields an Escape typed inside a dialog (marked here), which the dialog then closes on
const YIELDED = new WeakSet()

export function yieldEscapeToDialog(event) {
  if (!event.target?.closest?.('[role="dialog"]')) return
  event.preventDefault()
  YIELDED.add(event)
}

export const escapeYielded = (event) => YIELDED.has(event)
