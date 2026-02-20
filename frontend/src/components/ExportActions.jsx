/**
 * ExportActions — Reusable inline export buttons with contextual password field
 * 
 * When user clicks a format needing a password (P12), the buttons are replaced
 * by an inline password input + export/cancel buttons.
 * 
 * Usage:
 *   <ExportActions onExport={fn} hasPrivateKey={bool} variant="ghost|secondary" />
 */
import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Download, X, Lock } from '@phosphor-icons/react'
import { Button } from './Button'
import { cn } from '../lib/utils'

const FORMATS = [
  { key: 'pem', label: 'PEM', needsKey: false, needsPassword: false },
  { key: 'der', label: 'DER', needsKey: false, needsPassword: false },
  { key: 'pkcs7', label: 'P7B', needsKey: false, needsPassword: false },
  { key: 'pkcs12', label: 'P12', needsKey: true, needsPassword: true },
]

export function ExportActions({ 
  onExport, 
  hasPrivateKey = false,
  variant = 'ghost',
  size = 'xs',
  className 
}) {
  const { t } = useTranslation()
  const [passwordMode, setPasswordMode] = useState(false)
  const [password, setPassword] = useState('')
  const inputRef = useRef(null)

  useEffect(() => {
    if (passwordMode && inputRef.current) {
      inputRef.current.focus()
    }
  }, [passwordMode])

  const handleFormatClick = (format) => {
    if (format.needsPassword) {
      setPasswordMode(true)
      setPassword('')
      return
    }
    onExport(format.key)
  }

  const handlePasswordExport = () => {
    if (password.length < 4) return
    onExport('pkcs12', { password })
    setPasswordMode(false)
    setPassword('')
  }

  const handleCancel = () => {
    setPasswordMode(false)
    setPassword('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handlePasswordExport()
    if (e.key === 'Escape') handleCancel()
  }

  const formats = FORMATS.filter(f => !f.needsKey || hasPrivateKey)

  if (passwordMode) {
    return (
      <div className={cn('flex items-center gap-1.5 p-1 rounded-lg bg-tertiary-op50', className)}>
        <Lock size={14} className="text-text-tertiary shrink-0 ml-1" />
        <input
          ref={inputRef}
          type="text"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t('common.password', 'Password')}
          style={{ WebkitTextSecurity: 'disc', textSecurity: 'disc' }}
          className={cn(
            'w-24 sm:w-32 h-6 px-2 text-xs rounded-md border border-border bg-bg-primary text-text-primary',
            'placeholder:text-text-tertiary focus:outline-none focus:ring-1 focus:ring-accent-primary-op50 focus:border-accent-primary'
          )}
        />
        <Button 
          size="xs" 
          variant="primary" 
          onClick={handlePasswordExport} 
          disabled={password.length < 4}
          className="!h-6 !px-2 !text-xs"
        >
          <Download size={12} /> P12
        </Button>
        <button
          onClick={handleCancel}
          className="p-0.5 rounded hover:bg-bg-secondary text-text-tertiary hover:text-text-primary transition-colors"
        >
          <X size={14} />
        </button>
      </div>
    )
  }

  return (
    <div className={cn('flex flex-wrap gap-1 p-1 rounded-lg bg-tertiary-op50', className)}>
      {formats.map(f => (
        <Button 
          key={f.key} 
          size={size} 
          variant={variant} 
          onClick={() => handleFormatClick(f)} 
          className="!px-2 hover:bg-bg-secondary"
        >
          <Download size={12} /> {f.label}
        </Button>
      ))}
    </div>
  )
}
