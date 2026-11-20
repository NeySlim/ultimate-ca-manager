/** Loading state of an inspector object: bars where the three columns will be. */
import { useTranslation } from 'react-i18next'

const width = (i, base, spread) => `${base + ((i * 37) % spread)}%`

export function DetailSkeleton() {
  const { t } = useTranslation()
  return (
    <div className="ins-object" aria-busy="true" data-testid="inspector-skeleton">
      <div className="ins-heading"><span className="ins-sk" style={{ width: 220, height: 14 }} /></div>
      <div className="ins-sk-panel" aria-hidden="true">
        {[0, 1, 2].map((c) => (
          <div key={c} className="ins-sk-col">
            <span className="ins-sk is-thin" style={{ width: '40%' }} />
            {[0, 1, 2, 3].map((i) => <span key={i} className="ins-sk" style={{ width: width(i + c, 45, 45) }} />)}
          </div>
        ))}
      </div>
      <p className="sr-only" role="status">{t('common.loading')}</p>
    </div>
  )
}
