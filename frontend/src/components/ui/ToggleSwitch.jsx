/**
 * ToggleSwitch - a setting on or off, drawn as the Atelier check line: a 16 px native
 * checkbox and its label on one line (`.checkbox-line`), an optional description under the label.
 * The name keeps its old API; `size` is accepted and ignored (one geometry).
 */
import { useId } from 'react'
import { cn } from '../../lib/utils'

export function ToggleSwitch({
  checked = false,
  onChange,
  disabled = false,
  // eslint-disable-next-line no-unused-vars
  size,
  label,
  description,
  className = '',
  ...rest
}) {
  const id = useId()
  const handleChange = (e) => {
    if (!disabled && onChange) onChange(e.target.checked)
  }

  const box = (
    <input
      type="checkbox"
      checked={!!checked}
      disabled={disabled}
      onChange={handleChange}
      aria-labelledby={label ? `${id}-label` : undefined}
      aria-describedby={description ? `${id}-desc` : undefined}
      {...rest}
      className={label ? undefined : className || undefined}
    />
  )

  if (!label) return box

  // The label names the box; the description is linked to it, outside the name.
  return (
    <label className={cn('ui-check-line', description && 'has-desc', disabled && 'is-disabled', className)}>
      {box}
      <span className="ui-check-text">
        <span id={`${id}-label`}>{label}</span>
        {description && <small id={`${id}-desc`}>{description}</small>}
      </span>
    </label>
  )
}

export default ToggleSwitch
