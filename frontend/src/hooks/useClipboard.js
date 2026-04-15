/**
 * useClipboard - Centralized copy-to-clipboard hook
 * 
 * Replaces duplicated navigator.clipboard patterns across:
 * CertificateDetails, DetailCard, CADetails, TrustCertDetails, TagsInput
 */
import { useState, useCallback, useRef } from 'react'

export function useClipboard(timeout = 2000) {
  const [copiedKey, setCopiedKey] = useState(null)
  const timerRef = useRef(null)

  const copy = useCallback(async (text, key = '_default') => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(String(text))
      } else {
        // Fallback for non-secure contexts
        const textarea = document.createElement('textarea')
        textarea.value = String(text)
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        document.body.removeChild(textarea)
      }
      setCopiedKey(key)
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => setCopiedKey(null), timeout)
      return true
    } catch {
      return false
    }
  }, [timeout])

  const isCopied = useCallback((key = '_default') => {
    return copiedKey === key
  }, [copiedKey])

  return { copy, isCopied, copied: copiedKey !== null }
}
