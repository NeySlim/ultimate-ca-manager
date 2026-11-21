/**
 * The mockup's pill(label, tone) and badge(): `.badge` coloured by its tone, with the tone's icon,
 * so the colour is never the only signal. tone: 'good' | 'warn' | 'bad' | 'muted'.
 */
import { Icon } from './Icon'
import { TONE_ICONS } from './helpers'

export function Pill({ label, tone, icon }) {
  return <span className={tone ? `badge ${tone}` : 'badge'}><Icon name={icon || TONE_ICONS[tone] || 'check'} />{label}</span>
}

export default Pill
