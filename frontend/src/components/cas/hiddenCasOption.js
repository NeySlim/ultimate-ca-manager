/**
 * In a native select of the mockup the same link is its last option, as in the issue form:
 * choosing it shows or hides the hidden CAs, any other choice goes to onChange.
 */
export const SHOW_HIDDEN_CAS = '__hidden_cas__'
export function withHiddenCas(options, { count, shown, t }) {
  if (!count) return options
  return [...options, { value: SHOW_HIDDEN_CAS, label: shown ? t('cas.hideHiddenCas') : t('cas.showHiddenCas', { count }) }]
}
export const pickOrToggle = (onChange, onToggle) => (value) => (value === SHOW_HIDDEN_CAS ? onToggle() : onChange(value))
