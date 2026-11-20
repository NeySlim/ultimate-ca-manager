/**
 * Due date of the list template: the day, then how far it is in a short form
 * ("3 d", "5 mo", "1 y 4 mo", "Expired"), coloured by urgency. The exact date and time
 * and the long wording show on hover; the date is no tab stop of its row.
 */
import { useTranslation } from 'react-i18next'
import { cn, formatDate } from '../../lib/utils'
import { dueTone, relativeDue, relativeShort } from '../../lib/relativeTime'
import './list.css'

/**
 * @param {string|Date} date
 * @param {number} [warnDays]  days inside which the date is a warning
 * @param {''|'warn'|'bad'} [tone]  overrides the tone worked out from the date
 * @param {string|null} [relative]  overrides the relative wording; null shows the day alone
 */
export function DueDate({ date, warnDays = 7, tone, relative, now, className }) {
  const { t } = useTranslation()
  const time = date ? new Date(date) : null
  if (!time || Number.isNaN(time.getTime())) return <span className={cn('lv-due', className)}>—</span>
  const shownTone = tone ?? dueTone(date, { now, warnDays })
  const far = relative === undefined ? relativeShort(date, t, { now }) : relative
  const tip = [formatDate(date, { time: true }), relative === undefined ? relativeDue(date, t, { now }) : null].filter(Boolean).join(' · ')
  return (
    <span className={cn('lv-due lv-tip', shownTone && `is-${shownTone}`, className)} data-tip={tip}>
      <time dateTime={time.toISOString()}>{formatDate(date, { time: false })}</time>
      {far && <span className="lv-due-rel">{far}</span>}
    </span>
  )
}

export default DueDate
