/**
 * Opens a CA of a certificate's chain in the inspector. The chain the API returns
 * names its CAs only, so the list of CAs is read once, on the first click.
 * Null when the user cannot read the CAs: the chain then shows plain names.
 */
import { useCallback, useRef } from 'react'
import { usePermission } from '../../../hooks'
import { casService } from '../../../services'

export function useOpenCa(cert, onOpenCa) {
  const { hasPermission } = usePermission()
  const list = useRef(null)
  const open = useCallback(async (name, { issuing = false } = {}) => {
    if (!list.current) {
      const res = await casService.getAll()
      list.current = res?.data || []
    }
    // The issuing CA is the one the certificate references; the others are found by name
    const ca = (issuing && cert?.caref && list.current.find((c) => c.refid === cert.caref))
      || list.current.find((c) => (c.common_name || c.descr) === name)
    if (ca) onOpenCa?.(ca.id)
  }, [cert?.caref, onOpenCa])
  return onOpenCa && hasPermission('read:cas') ? open : null
}
