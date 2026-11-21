/**
 * The HSM mark of an SSH authority (the SSH CA page): the provider and key label in its tooltip.
 */
export function HsmBadge({ ca, t }) {
  // An SSH CA records the same fact as key_source rather than uses_hsm
  if (!ca?.uses_hsm && ca?.key_source !== 'hsm') return null
  const tip = [ca.hsm_provider_name, ca.hsm_key_label].filter(Boolean).join(' / ')
  return (
    <span
      className="shrink-0 px-1.5 py-0.5 rounded-md text-2xs font-semibold badge-bg-violet"
      title={tip || t('cas.detail.hsmBacked')}
    >
      HSM
    </span>
  )
}
