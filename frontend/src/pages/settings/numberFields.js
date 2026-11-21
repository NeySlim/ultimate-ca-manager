/**
 * A whole number typed in a text field (the mockup's numeric fields): an empty entry stays empty
 * and an unreadable one stays as typed, both refused by the checks at the save, never replaced
 * by a default under the user's fingers.
 */
const blank = (v) => v === '' || v === null || v === undefined || Number.isNaN(v)
const digits = (v) => /^\d+$/.test(String(v).trim())

/** The value a field shows: '' when empty, the typed text when unreadable, else `as(number)`. */
export const shownNumber = (value, as = (v) => v) => {
  if (blank(value)) return ''
  if (typeof value === 'string' && !digits(value)) return value
  return as(Number(value))
}

/** The draft a typed entry makes: '' when empty, the text when unreadable, else `as(number)`. */
export const typedNumber = (e, as = (v) => v) => {
  const text = e.target.value.trim()
  if (text === '') return ''
  return digits(text) ? as(Number(text)) : e.target.value
}
