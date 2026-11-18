/** A password the policy accepts whatever the clock and the dice give: no four characters in a row without a `!`. */
export function strongPassword() {
  const raw = Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
  return `E2e!${raw.match(/.{1,3}/g)!.join('!')}!Qz9`
}
