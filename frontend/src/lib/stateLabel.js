/** A status the server names in English, in the user's language; an unknown one reads as sent. */
export function stateLabel(t, value) {
  if (value === null || value === undefined || value === '') return '–'
  const raw = String(value)
  return t(`common.states.${raw.toLowerCase()}`, raw)
}
