/**
 * ExportDropdown Component
 * Dropdown button for exporting in multiple formats with options
 */
import { Export, Key, Link, Lock } from '@phosphor-icons/react'
import { Dropdown } from './Dropdown'
import { useNotification } from '../contexts/NotificationContext'
import { useTranslation } from 'react-i18next'

export function ExportDropdown({ 
  onExport, 
  disabled = false, 
  formats = ['pem', 'pem-key', 'pem-chain', 'pem-full', 'der', 'pkcs12', 'jks'],
  hasPrivateKey = true 
}) {
  const { showPrompt } = useNotification()
  const { t } = useTranslation()
  
  const formatConfig = {
    'pem': { 
      labelKey: 'export.formatOptions.pemOnly', 
      icon: <Export size={16} />,
      format: 'pem',
      options: {}
    },
    'pem-key': { 
      labelKey: 'export.formatOptions.pemWithKey', 
      icon: <Key size={16} />,
      format: 'pem',
      options: { includeKey: true },
      requiresKey: true
    },
    'pem-chain': { 
      labelKey: 'export.formatOptions.pemWithChain', 
      icon: <Link size={16} />,
      format: 'pem',
      options: { includeChain: true }
    },
    'pem-full': { 
      labelKey: 'export.formatOptions.fullBundle', 
      icon: <Lock size={16} />,
      format: 'pem',
      options: { includeKey: true, includeChain: true },
      requiresKey: true
    },
    'der': { 
      labelKey: 'export.formatOptions.derBinary', 
      icon: <Export size={16} />,
      format: 'der',
      options: {}
    },
    'pkcs12': { 
      labelKey: 'export.formatOptions.pkcs12', 
      icon: <Lock size={16} />,
      format: 'pkcs12',
      options: { password: true }, // Will prompt for password
      requiresKey: true
    },
    'jks': { 
      labelKey: 'export.formatOptions.jks', 
      icon: <Lock size={16} />,
      format: 'jks',
      options: { password: true, includeChain: true },
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
        label: t(config.labelKey),
        icon: config.icon,
        onClick: async () => {
          if (config.options.password) {
            // Prompt for PKCS12 password
            const password = await showPrompt('Enter password for PKCS#12 file:', {
              title: 'Export PKCS#12',
              type: 'password',
              placeholder: 'Password',
              confirmText: 'Export'
            })
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
          {t('export.title')}
        </div>
      }
      items={items}
      disabled={disabled}
      size="default"
      variant="primary"
    />
  )
}
