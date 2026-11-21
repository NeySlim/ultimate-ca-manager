/** Hooks and readers of the mockup's form fields (Form.jsx), kept apart from its components. */
import { useEffect, useState } from 'react'
import { fetchPasswordStrength, localPasswordStrength } from '../../lib/passwordStrength'

/**
 * The server's reading of a password, debounced, the last answer winning; the offline reading
 * shows at once so the gauge never sits blank. null while there is nothing to read.
 */
export function usePasswordStrength(password, enabled = true) {
  const [reading, setReading] = useState(null)
  useEffect(() => {
    if (!enabled || !password) { setReading(null); return undefined }
    let cancelled = false
    setReading((previous) => previous || localPasswordStrength(password))
    const timer = setTimeout(() => {
      fetchPasswordStrength(password).then((result) => { if (!cancelled) setReading(result) })
    }, 300)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [enabled, password])
  return reading
}

const PEM_HEAD = '-----BEGIN'

/** A file's content as the product sends it: PEM as text, anything else as `BASE64:` and its bytes. */
const readBytes = (file) => (typeof file.arrayBuffer === 'function' ? file.arrayBuffer() : new Promise((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => resolve(reader.result)
  reader.onerror = () => reject(reader.error)
  reader.readAsArrayBuffer(file)
}))

export async function fileContent(file) {
  const bytes = new Uint8Array(await readBytes(file))
  if (String.fromCharCode(...bytes.slice(0, 11)).startsWith(PEM_HEAD)) return new TextDecoder().decode(bytes)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
  return `BASE64:${btoa(binary)}`
}
