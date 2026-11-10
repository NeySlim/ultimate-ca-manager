/**
 * Input Component - Text input with label, error, and enhanced focus
 * Supports password fields with show/hide toggle and strength indicator
 * Supports credential fields with "already set" indicator
 */
import { forwardRef, useEffect, useMemo, useState } from 'react'
import { Eye, EyeSlash, CheckCircle } from '@phosphor-icons/react'
import { cn } from '../lib/utils'
import { useTranslation } from 'react-i18next'
import { barsForScore, fetchPasswordStrength, localPasswordStrength } from '../lib/passwordStrength'

// How the meter paints a level. The level itself comes from the server
// (lib/passwordStrength): the five-property count this used to do read
// "strong" where the server said "fair", and a meter that overstates is
// worse than no meter.
const LEVEL_STYLE = {
  weak: { labelKey: 'passwordStrength.weak', color: 'bg-accent-danger', text: 'text-accent-danger' },
  fair: { labelKey: 'passwordStrength.fair', color: 'bg-accent-warning', text: 'text-accent-warning' },
  good: { labelKey: 'passwordStrength.good', color: 'bg-accent-warning', text: 'text-accent-warning' },
  strong: { labelKey: 'passwordStrength.strong', color: 'bg-accent-success', text: 'text-accent-success' },
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
  placeholder,
  required,
  noAutofill,  // Use text+CSS masking to prevent password manager detection
  ...props 
}, ref) {
  const { t } = useTranslation()
  const [showPassword, setShowPassword] = useState(false)
  const [internalValue, setInternalValue] = useState('')
  
  const isPassword = type === 'password'
  // noAutofill: render as text with CSS masking to hide from password managers
  const useTextMasking = isPassword && noAutofill && !showPassword
  const inputType = isPassword && showPassword ? 'text' : (useTextMasking ? 'text' : type)
  
  // Track value for strength indicator
  const handleChange = (e) => {
    setInternalValue(e.target.value)
    props.onChange?.(e)
  }
  
  // The server scores the password. The request is debounced and the last
  // answer wins, so a burst of keystrokes cannot paint an older verdict.
  const passwordValue = props.value ?? internalValue
  const wantsStrength = Boolean(isPassword && showStrength)
  const [strengthResult, setStrengthResult] = useState(null)

  useEffect(() => {
    if (!wantsStrength || !passwordValue) {
      setStrengthResult(null)
      return undefined
    }
    let cancelled = false
    // Show the offline reading straight away so the meter never sits blank,
    // then replace it with the server's.
    setStrengthResult((previous) => previous || localPasswordStrength(passwordValue))
    const timer = setTimeout(() => {
      fetchPasswordStrength(passwordValue).then((result) => {
        if (!cancelled) setStrengthResult(result)
      })
    }, 300)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [wantsStrength, passwordValue])

  const strength = useMemo(() => {
    if (!wantsStrength || !strengthResult) return null
    const style = LEVEL_STYLE[strengthResult.level] || LEVEL_STYLE.weak
    return { ...style, bars: barsForScore(strengthResult.score) }
  }, [wantsStrength, strengthResult])

  // Determine placeholder for existing secret values
  const effectivePlaceholder = hasExistingValue && isPassword
    ? '••••••••••••'
    : placeholder

  return (
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <label className="block text-xs font-medium text-text-secondary leading-[20px]">
          <span className="flex items-center gap-1 h-[20px]">
            {typeof label === 'string' ? label : label}
            {required && !hasExistingValue && <span className="status-danger-text">*</span>}
            {hasExistingValue && (
              <span className="inline-flex items-center gap-1 px-1.5 text-xs font-medium bg-status-success-op20 text-status-success rounded leading-[16px]">
                <CheckCircle size={10} weight="fill" />
                {t('common.set')}
              </span>
            )}
          </span>
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
            "w-full px-2.5 py-1.5 bg-bg-tertiary border rounded-md text-sm text-text-primary placeholder-text-tertiary",
            "transition-all duration-150",
            "hover:border-text-tertiary",
            "focus:outline-none focus:border-accent-primary",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            error ? "border-accent-danger" : "border-border",
            icon && "pl-9",
            isPassword && "pr-10"
          )}
          style={{
            '--focus-shadow': 'color-mix(in srgb, var(--accent-primary) 15%, transparent)',
            ...(useTextMasking ? { WebkitTextSecurity: 'disc', textSecurity: 'disc' } : {})
          }}
          onFocus={(e) => {
            e.target.style.boxShadow = '0 0 0 3px var(--focus-shadow), 0 1px 2px color-mix(in srgb, var(--accent-primary) 10%, transparent)';
          }}
          onBlur={(e) => {
            e.target.style.boxShadow = '';
          }}
          onChange={handleChange}
          placeholder={effectivePlaceholder}
          required={required && !hasExistingValue}
          autoComplete={noAutofill ? 'off' : undefined}
          {...props}
        />
        
        {/* Password toggle -- hidden when there's nothing typed to reveal.
            An "already set" field shows a literal '••••••••' placeholder
            (never a real loaded secret, which is never sent to the browser),
            and placeholders are never masked/unmasked by type or CSS in any
            browser -- showing the toggle there just invites a user to click
            "reveal" on text that was never masked in the first place. */}
        {isPassword && (props.value || internalValue) && (
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
      {strength && passwordValue && (
        <div className="space-y-1">
          <div className="flex gap-1">
            {[...Array(5)].map((_, i) => (
              <div
                key={i}
                className={cn(
                  "h-1 flex-1 rounded-full transition-colors",
                  i < strength.bars ? strength.color : "bg-border"
                )}
              />
            ))}
          </div>
          <p className={cn("text-xs", strength.text)}>
            {t(strength.labelKey)}
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
