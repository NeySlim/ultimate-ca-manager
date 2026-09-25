import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMobile, useWindowManager } from '../contexts'
import { usePermission } from '.'

// Deep link of each type's page and the scope its detail is read with
const ENTITIES = {
  certificate: { route: '/certificates', resource: 'certificates' },
  ca: { route: '/cas', resource: 'cas' },
  truststore: { route: '/truststore', resource: 'truststore' },
}

/**
 * Open an entity's detail from any page: a floating window on desktop, its
 * page's deep link on mobile, where floating windows are not shown.
 */
export function useOpenEntity() {
  const { isMobile } = useMobile()
  const { openWindow } = useWindowManager()
  const { canRead } = usePermission()
  const navigate = useNavigate()
  return useCallback((type, id) => {
    const entity = ENTITIES[type]
    if (!id || !entity || !canRead(entity.resource)) return
    if (isMobile) navigate(`${entity.route}/${id}`)
    else openWindow(type, id)
  }, [isMobile, openWindow, canRead, navigate])
}
