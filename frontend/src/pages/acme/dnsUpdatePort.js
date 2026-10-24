/**
 * Returns the port as an integer when it is valid: 0 (disabled) or 1024-65535.
 * Returns null otherwise. The server applies the same rule.
 */
export function parseDnsUpdatePort(raw) {
  const text = String(raw ?? '').trim()
  if (!/^\d+$/.test(text)) return null
  const port = parseInt(text, 10)
  if (port === 0 || (port >= 1024 && port <= 65535)) return port
  return null
}
