/**
 * Input Component - Text input with label, error, and enhanced focus
 * Supports password fields with show/hide toggle and strength indicator
 * Supports credential fields with "already set" indicator
 */
import { forwardRef, useState, useMemo } from 'react'
import { Eye, EyeSlash, CheckCircle } from '@phosphor-icons/react'
import { cn } from '../lib/utils'
import { useTranslation } from 'react-i18next'

// Password strength calculation
const getPasswordStrength = (password) => {
  if (!password) return { score: 0, label: '', color: '' }
  
  let score = 0
  if (password.length >= 8) score++
  if (password.length >= 12) score++
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score++
  if (/\d/.test(password)) score++
  if (/[^a-zA-Z0-9]/.test(password)) score++
  
  const levels = [
    { label: 'Weak', color: 'bg-accent-danger' },
    { label: 'Weak', color: 'bg-accent-danger' },
    { label: 'Fair', color: 'bg-accent-warning' },
    { label: 'Good', color: 'bg-accent-warning' },
    { label: 'Strong', color: 'bg-accent-success' },
    { label: 'Strong', color: 'bg-accent-success' }
  ]
  
  return { score, ...levels[score] }
}

export const Input = forwardRef(function Input({ 
  label, 
  error, 
  helperText,
  icon,
  className,
  type,
  showStrength,
  hasExistingValue,  // Shows "Set" badge and "enter new to change" hint
  ...props 
}, ref) {
  const { t } = useTranslation()
  const [showPassword, setShowPassword] = useState(false)
  const [internalValue, setInternalValue] = useState('')
  
  const isPassword = type === 'password'
  const inputType = isPassword && showPassword ? 'text' : type
  
  // Track value for strength indicator
  const handleChange = (e) => {
    setInternalValue(e.target.value)
    props.onChange?.(e)
  }
  
  const strength = useMemo(() => {
    if (!isPassword || !showStrength) return null
    return getPasswordStrength(props.value ?? internalValue)
  }, [isPassword, showStrength, props.value, internalValue])

  // Determine placeholder for existing secret values
  const effectivePlaceholder = hasExistingValue && isPassword && !props.placeholder
    ? '••••••••••••'
    : props.placeholder

  return (
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <label className="block text-xs font-medium text-text-secondary">
          <span className="flex items-center gap-2">
            {typeof label === 'string' ? label : label}
            {hasExistingValue && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium bg-status-success/20 text-status-success rounded">
                <CheckCircle size={10} weight="fill" />
                {t('common.set')}
              </span>
            )}
          </span>
          {props.required && !hasExistingValue && <span className="status-danger-text ml-1">*</span>}
        </label>
      )}
      
      <div className="relative">
        {icon && (
          <div className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary">
            {icon}
          </div>
        )}
        <input
          ref={ref}
          type={inputType}
          className={cn(
            "w-full px-3 py-2 bg-bg-tertiary border rounded-lg text-sm text-text-primary placeholder-text-tertiary",
            "transition-all duration-150",
            "hover:border-text-tertiary",
            "focus:outline-none focus:border-accent-primary",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            error ? "border-accent-danger" : "border-border",
            icon && "pl-9",
            isPassword && "pr-10"
          )}
          style={{
            '--focus-shadow': 'color-mix(in srgb, var(--accent-primary) 15%, transparent)'
          }}
          onFocus={(e) => {
            e.target.style.boxShadow = '0 0 0 3px var(--focus-shadow), 0 1px 2px color-mix(in srgb, var(--accent-primary) 10%, transparent)';
          }}
          onBlur={(e) => {
            e.target.style.boxShadow = '';
          }}
          onChange={handleChange}
          placeholder={effectivePlaceholder}
          required={props.required && !hasExistingValue}
          {...props}
        />
        
        {/* Password toggle */}
        {isPassword && (
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-text-secondary transition-colors"
            tabIndex={-1}
          >
            {showPassword ? <EyeSlash size={18} /> : <Eye size={18} />}
          </button>
        )}
      </div>
      
      {/* Password strength indicator */}
      {strength && (props.value ?? internalValue) && (
        <div className="space-y-1">
          <div className="flex gap-1">
            {[...Array(5)].map((_, i) => (
              <div
                key={i}
                className={cn(
                  "h-1 flex-1 rounded-full transition-colors",
                  i < strength.score ? strength.color : "bg-border"
                )}
              />
            ))}
          </div>
          <p className={cn("text-xs", strength.score >= 4 ? "text-accent-success" : strength.score >= 2 ? "text-accent-warning" : "text-accent-danger")}>
            {strength.label}
          </p>
        </div>
      )}

      {error && (
        <p className="text-xs status-danger-text">{error}</p>
      )}
      
      {/* Helper text - show "enter new to change" for existing values */}
      {hasExistingValue && !error && (
        <p className="text-xs text-text-tertiary italic">{t('common.enterNewToChange')}</p>
      )}
      
      {helperText && !error && !hasExistingValue && (
        <p className="text-xs text-text-tertiary">{helperText}</p>
      )}
    </div>
  )
})
