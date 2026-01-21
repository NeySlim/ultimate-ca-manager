/**
 * Conditional className utility
 * Merges class names conditionally
 * 
 * Usage:
 *   classNames('btn', isActive && 'active', 'btn-primary')
 *   → 'btn active btn-primary' (if isActive is true)
 */
export function classNames(...classes) {
  return classes.filter(Boolean).join(' ');
}

export default classNames;
