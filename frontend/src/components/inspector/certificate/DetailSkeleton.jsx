/**
 * Loading state of an inspector object, as the mockup's: the heading at its height, the
 * section tabs already in place (inert), then bars where the three columns will be.
 */
import { useTranslation } from 'react-i18next'

const width = (i, base, spread) => `${base + ((i * 37) % spread)}%`

export function DetailSkeleton({ sections = null }) {
  const { t } = useTranslation()
  return (
    <div className="ins-object" aria-busy="true" data-testid="inspector-skeleton">
      <div className="ins-heading is-skeleton" aria-hidden="true">
        <span className="ins-sk" style={{ width: 220, height: 14 }} />
        <span className="ins-sk is-button" />
      </div>
      {sections?.length > 0 && (
        <div className="ins-detail-tabs is-skeleton" aria-hidden="true" data-testid="inspector-skeleton-sections">
          {sections.map((s, i) => (
            <span key={s} className="ins-sk-tab" data-current={i === 0 || undefined}>{t(`inspector.sections.${s}`)}</span>
          ))}
        </div>
      )}
      <div className={sections?.length > 0 ? 'ins-panel' : undefined}>
        <div className="ins-sk-panel" aria-hidden="true">
          {[0, 1, 2].map((c) => (
            <div key={c} className="ins-sk-col">
              <span className="ins-sk is-thin" style={{ width: '40%' }} />
              {[0, 1, 2, 3].map((i) => <span key={i} className="ins-sk" style={{ width: width(i + c, 45, 45) }} />)}
            </div>
          ))}
        </div>
      </div>
      <p className="sr-only" role="status">{t('common.loading')}</p>
    </div>
  )
}
