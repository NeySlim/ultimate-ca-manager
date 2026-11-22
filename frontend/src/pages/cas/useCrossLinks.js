/**
 * Who cross-certified whom, for the links of the tree and the side panel: the cross certificates
 * of the first holders (CROSS_LINK_HOLDERS), as { from, to } authority ids, each pair once.
 */
import { useEffect, useState } from 'react'
import { casService } from '../../services'

// Cross-certificate issuers are read per authority: only the first holders are asked
const CROSS_LINK_HOLDERS = 12

export function useCrossLinks(cas) {
  const [crossLinks, setCrossLinks] = useState([])
  const crossKey = cas.filter((c) => c.cross_certificate_count > 0).map((c) => `${c.id}:${c.cross_certificate_count}`).join(',')
  useEffect(() => {
    const holders = cas.filter((c) => c.cross_certificate_count > 0).slice(0, CROSS_LINK_HOLDERS)
    if (holders.length === 0) { setCrossLinks([]); return undefined }
    let live = true
    const byRef = new Map(cas.map((c) => [c.refid, c.id]))
    Promise.all(holders.map((ca) => casService.getCrossCertificates(ca.id)
      .then((res) => (res.data || []).map((x) => ({ from: byRef.get(x.issuer_caref), to: ca.id })))
      .catch(() => [])))
      .then((lists) => {
        if (!live) return
        const seen = new Set()
        setCrossLinks(lists.flat().filter((l) => {
          const key = `${l.from}-${l.to}`
          if (l.from === undefined || l.from === l.to || seen.has(key)) return false
          seen.add(key)
          return true
        }))
      })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crossKey])
  return crossLinks
}
