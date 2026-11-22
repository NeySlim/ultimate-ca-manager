/** The comparison in a detached window: its title counts the certificates. */
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { CompareView } from './CompareView'

export default function CompareFloat({ ids, onTitle }) {
  const { t } = useTranslation()
  const title = t('compare.countTitle', { count: ids.length })
  useEffect(() => { onTitle?.(title) }, [title]) // eslint-disable-line react-hooks/exhaustive-deps
  return <CompareView ids={ids} />
}
