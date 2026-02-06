/**
 * Permission Hook - Check user permissions
 */
import { useAuth } from '../contexts/AuthContext'

export function usePermission() {
  const { permissions } = useAuth()

  /**
   * Check if user has a specific permission
   * Supports wildcards: *, read:*, write:*
   */
  const hasPermission = (required) => {
    if (!required) return true
    if (!permissions || permissions.length === 0) return false

    // Full admin access
    if (permissions.includes('*')) return true

    // Exact match
    if (permissions.includes(required)) return true

    // Check category wildcard (read:* matches read:cas)
    if (required.includes(':')) {
      const [category] = required.split(':')
      if (permissions.includes(`${category}:*`)) return true
    }

    return false
  }

  /**
   * Convenience methods for common permission checks
   */
  const canRead = (resource) => hasPermission(`read:${resource}`)
  const canWrite = (resource) => hasPermission(`write:${resource}`)
  const canDelete = (resource) => hasPermission(`delete:${resource}`)
  const isAdmin = () => permissions.includes('*')

  return {
    hasPermission,
    canRead,
    canWrite,
    canDelete,
    isAdmin,
    permissions,
  }
}
