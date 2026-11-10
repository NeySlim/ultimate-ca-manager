import { useCallback } from 'react'
import { useInspector } from '../contexts'
import { usePermission } from '.'

// The scope each type's detail is read with
const RESOURCES = {
  certificate: 'certificates',
  ca: 'cas',
  truststore: 'truststore',
}

/** Open an entity's detail in the inspector, from any page. */
export function useOpenEntity() {
  const { openEntity } = useInspector()
  const { canRead } = usePermission()
  return useCallback((type, id, opts) => {
    const resource = RESOURCES[type]
    if (!id || !resource || !canRead(resource)) return
    // The options argument is passed only when there is one
    if (opts) openEntity(type, id, opts)
    else openEntity(type, id)
  }, [openEntity, canRead])
}
