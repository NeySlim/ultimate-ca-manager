import { useSearchParams } from 'react-router-dom'

/**
 * The object a link points at: the first of `names` carrying a whole number in the URL.
 * The work queue's links and the pages read the same names (contracts/queue_links.json).
 */
export function useLinkedId(...names) {
  const [params] = useSearchParams()
  for (const name of names) {
    const value = params.get(name)
    if (value && /^\d+$/.test(value)) return value
  }
  return null
}
