/**
 * Input Component - the Atelier field: 12 px label, 36 px control, hint or error under it
 * Supports password fields with show/hide toggle and strength indicator
 * Supports credential fields with "already set" indicator
 */
import { forwardRef, useEffect, useId, useMemo, useState } from 'react'
import { Eye, EyeSlash, CheckCircle, WarningCircle } from '@phosphor-icons/react'
import { cn } from '../lib/utils'
import { useTranslation } from 'react-i18next'
import { barsForScore, fetchPasswordStrength, localPasswordStrength } from '../lib/passwordStrength'

// How the meter paints a level. The level itself comes from the server
// (lib/passwordStrength): the five-property count this used to do read
// "strong" where the server said "fair", and a meter that overstates is
// worse than no meter.
const LEVEL_STYLE = {
  weak: { labelKey: 'passwordStrength.weak', tone: 'is-bad' },
  fair: { labelKey: 'passwordStrength.fair', tone: 'is-warn' },
  good: { labelKey: 'passwordStrength.good', tone: 'is-warn' },
  strong: { labelKey: 'passwordStrength.strong', tone: 'is-good' },
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
  // The label names the field (assistive technologies, getByLabelText)
  const autoId = useId()
  const fieldId = props.id ?? autoId
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

  const helpId = `${fieldId}-help`
  const errorId = `${fieldId}-error`
  const hintText = hasExistingValue ? t('common.enterNewToChange') : helperText
  const describedBy = [error ? errorId : null, !error && hintText ? helpId : null, props['aria-describedby']]
    .filter(Boolean).join(' ') || undefined
  const canReveal = isPassword && (props.value || internalValue)

  return (
    <div className={cn('ui-field', className)}>
      {label && (
        <label htmlFor={fieldId} className="ui-label">
          {label}
          {required && !hasExistingValue && <span className="ui-required" aria-hidden="true">*</span>}
          {hasExistingValue && (
            <span className="ui-set">
              <CheckCircle weight="fill" aria-hidden="true" />
              {t('common.set')}
            </span>
          )}
        </label>
      )}

      <div className="ui-control-wrap">
        {icon && <span className="ui-control-icon">{icon}</span>}
        <input
          ref={ref}
          type={inputType}
          className={cn('ui-control', icon && 'pl-9', isPassword && 'has-reveal')}
          style={useTextMasking ? { WebkitTextSecurity: 'disc', textSecurity: 'disc' } : undefined}
          onChange={handleChange}
          placeholder={effectivePlaceholder}
          required={required && !hasExistingValue}
          autoComplete={noAutofill ? 'off' : undefined}
          aria-invalid={error ? true : undefined}
          {...props}
          aria-describedby={describedBy}
          id={fieldId}
        />

        {/* Password toggle -- hidden when there's nothing typed to reveal.
            An "already set" field shows a literal '••••••••' placeholder
            (never a real loaded secret, which is never sent to the browser),
            and placeholders are never masked/unmasked by type or CSS in any
            browser -- showing the toggle there just invites a user to click
            "reveal" on text that was never masked in the first place. */}
        {canReveal && (
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="ui-reveal"
            aria-label={showPassword ? t('auth.page.hidePassword') : t('auth.page.showPassword')}
            tabIndex={-1}
          >
            {showPassword ? <EyeSlash aria-hidden="true" /> : <Eye aria-hidden="true" />}
          </button>
        )}
      </div>

      {/* Password strength indicator */}
      {strength && passwordValue && (
        <>
          <div className="ui-meter" aria-hidden="true">
            {[...Array(5)].map((_, i) => (
              <span key={i} className={i < strength.bars ? strength.tone : undefined} />
            ))}
          </div>
          <p className={cn('ui-meter-label', strength.tone)}>{t(strength.labelKey)}</p>
        </>
      )}

      {error && (
        <p id={errorId} className="ui-error"><WarningCircle aria-hidden="true" />{error}</p>
      )}

      {!error && hintText && (
        <p id={helpId} className="ui-help">{hintText}</p>
      )}
    </div>
  )
})
