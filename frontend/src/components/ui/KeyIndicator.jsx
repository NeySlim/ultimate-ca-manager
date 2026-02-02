/**
 * KeyIndicator - Shows if a certificate has a private key
 * Golden key = has private key, Greyed crossed key = no private key
 * Uses theme-aware colors with outline style
 */
import { Key, X } from '@phosphor-icons/react'

export function KeyIndicator({ hasKey, size = 14, showTooltip = true }) {
  if (hasKey) {
    return (
      <span 
        className="relative inline-flex items-center" 
        title={showTooltip ? "Private key available" : undefined}
      >
        <Key 
          size={size} 
          weight="regular"
          className="text-amber-500 dark:text-amber-400"
        />
      </span>
    )
  }
  
  return (
    <span 
      className="relative inline-flex items-center" 
      title={showTooltip ? "No private key" : undefined}
    >
      <Key 
        size={size} 
        weight="light"
        className="text-text-tertiary"
      />
      <X 
        size={size * 0.6} 
        weight="bold"
        className="absolute text-text-tertiary"
        style={{ 
          right: -1, 
          bottom: 0,
        }}
      />
    </span>
  )
}

export default KeyIndicator
