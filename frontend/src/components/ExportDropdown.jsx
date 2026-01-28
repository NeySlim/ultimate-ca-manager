/**
 * ExportDropdown Component
 * Dropdown button for exporting in multiple formats with options
 */
import { Export, Key, Link, Lock } from '@phosphor-icons/react'
import { Dropdown } from './Dropdown'

export function ExportDropdown({ 
  onExport, 
  disabled = false, 
  formats = ['pem', 'pem-key', 'pem-chain', 'pem-full', 'der', 'pkcs12'],
  hasPrivateKey = true 
}) {
  const formatConfig = {
    'pem': { 
      label: 'PEM (Certificate only)', 
      icon: <Export size={16} />,
      format: 'pem',
      options: {}
    },
    'pem-key': { 
      label: 'PEM + Private Key', 
      icon: <Key size={16} />,
      format: 'pem',
      options: { includeKey: true },
      requiresKey: true
    },
    'pem-chain': { 
      label: 'PEM + CA Chain', 
      icon: <Link size={16} />,
      format: 'pem',
      options: { includeChain: true }
    },
    'pem-full': { 
      label: 'Full Bundle (Cert + Key + Chain)', 
      icon: <Lock size={16} />,
      format: 'pem',
      options: { includeKey: true, includeChain: true },
      requiresKey: true
    },
    'der': { 
      label: 'DER (Binary)', 
      icon: <Export size={16} />,
      format: 'der',
      options: {}
    },
    'pkcs12': { 
      label: 'PKCS#12 (.p12)', 
      icon: <Lock size={16} />,
      format: 'pkcs12',
      options: { password: true }, // Will prompt for password
      requiresKey: true
    }
  }

  const items = formats
    .filter(f => {
      const config = formatConfig[f]
      if (!config) return false
      // Filter out options that need private key if not available
      if (config.requiresKey && !hasPrivateKey) return false
      return true
    })
    .map(f => {
      const config = formatConfig[f]
      return {
        label: config.label,
        icon: config.icon,
        onClick: () => {
          if (config.options.password) {
            // Prompt for PKCS12 password
            const password = window.prompt('Enter password for PKCS#12 file:')
            if (password) {
              onExport(config.format, { ...config.options, password })
            }
          } else {
            onExport(config.format, config.options)
          }
        }
      }
    })

  return (
    <Dropdown
      trigger={
        <div className="flex items-center gap-1.5">
          <Export size={16} />
          Export
        </div>
      }
      items={items}
      disabled={disabled}
    />
  )
}
