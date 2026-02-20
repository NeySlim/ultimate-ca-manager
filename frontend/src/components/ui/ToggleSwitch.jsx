/**
 * ToggleSwitch - Theme-aware toggle switch component
 * Uses CSS variables for full theme compatibility (dark, light, etc.)
 */

export function ToggleSwitch({ 
  checked = false, 
  onChange, 
  disabled = false,
  size = 'md',
  label,
  description,
  className = '' 
}) {
  const sizes = {
    sm: { track: 'w-8 h-[18px]', thumb: 'w-3.5 h-3.5', translate: 'translate-x-[14px]' },
    md: { track: 'w-10 h-[22px]', thumb: 'w-4 h-4', translate: 'translate-x-[18px]' },
    lg: { track: 'w-12 h-[26px]', thumb: 'w-5 h-5', translate: 'translate-x-[22px]' },
  }

  const s = sizes[size] || sizes.md

  const handleClick = () => {
    if (!disabled && onChange) {
      onChange(!checked)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      handleClick()
    }
  }

  const toggle = (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={`
        relative inline-flex items-center shrink-0 rounded-full 
        transition-colors duration-200 ease-in-out
        focus:outline-none focus:ring-2 focus:ring-accent-primary-op40 focus:ring-offset-1 focus:ring-offset-bg-primary
        ${s.track}
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
        ${checked ? 'bg-accent-primary' : 'bg-bg-tertiary border border-border'}
      `}
    >
      <span
        className={`
          inline-block rounded-full shadow-sm
          transition-transform duration-200 ease-in-out
          ${s.thumb}
          ${checked ? `${s.translate} bg-white` : 'translate-x-[3px] bg-text-tertiary'}
        `}
      />
    </button>
  )

  if (!label) {
    return <div className={className}>{toggle}</div>
  }

  return (
    <label 
      className={`flex items-center gap-3 p-2 rounded-lg transition-colors
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:bg-tertiary-op50'}
        ${className}
      `}
      onClick={(e) => e.preventDefault()}
    >
      {toggle}
      <div className="flex-1" onClick={handleClick}>
        <p className="text-sm text-text-primary font-medium">{label}</p>
        {description && <p className="text-xs text-text-secondary">{description}</p>}
      </div>
    </label>
  )
}

export default ToggleSwitch
