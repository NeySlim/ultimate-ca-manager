/**
 * Permissions Display Component
 * Shows role permissions in a clear, readable format
 */
import { Badge } from './Badge'
import { Lock, LockOpen, ShieldCheck } from '@phosphor-icons/react'

export function PermissionsDisplay({ role, permissions = [], description }) {
  if (!permissions || permissions.length === 0) {
    return <div className="text-sm text-text-secondary">No permissions</div>
  }

  // Check if admin (full access)
  if (permissions.includes('*')) {
    return (
      <div className="space-y-2">
        {description && (
          <p className="text-xs text-text-secondary">{description}</p>
        )}
        <div className="flex items-center gap-2 p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
          <ShieldCheck size={20} className="text-blue-500" weight="fill" />
          <span className="text-sm font-semibold text-blue-500">Full Access</span>
        </div>
      </div>
    )
  }

  // Group permissions by action
  const grouped = {
    read: [],
    write: [],
    delete: [],
    admin: []
  }

  permissions.forEach(perm => {
    if (perm === 'read:*') {
      grouped.read.push('All Resources')
    } else if (perm === 'write:*') {
      grouped.write.push('All Resources')
    } else if (perm === 'delete:*') {
      grouped.delete.push('All Resources')
    } else if (perm.includes(':')) {
      const [action, resource] = perm.split(':')
      if (grouped[action]) {
        grouped[action].push(resource.toUpperCase())
      }
    }
  })

  return (
    <div className="space-y-3">
      {description && (
        <p className="text-xs text-text-secondary">{description}</p>
      )}
      
      <div className="space-y-2">
        {/* Read permissions */}
        {grouped.read.length > 0 && (
          <div className="p-3 bg-green-500/5 border border-green-500/10 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <LockOpen size={16} className="text-green-500" />
              <span className="text-xs font-semibold text-green-500 uppercase">Read Access</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {grouped.read.map((resource, idx) => (
                <Badge key={idx} variant="success" size="sm">
                  {resource}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Write permissions */}
        {grouped.write.length > 0 && (
          <div className="p-3 bg-blue-500/5 border border-blue-500/10 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Lock size={16} className="text-blue-500" />
              <span className="text-xs font-semibold text-blue-500 uppercase">Write Access</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {grouped.write.map((resource, idx) => (
                <Badge key={idx} variant="info" size="sm">
                  {resource}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Delete permissions */}
        {grouped.delete.length > 0 && (
          <div className="p-3 bg-orange-500/5 border border-orange-500/10 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Lock size={16} className="text-orange-500" />
              <span className="text-xs font-semibold text-orange-500 uppercase">Delete Access</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {grouped.delete.map((resource, idx) => (
                <Badge key={idx} variant="warning" size="sm">
                  {resource}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
