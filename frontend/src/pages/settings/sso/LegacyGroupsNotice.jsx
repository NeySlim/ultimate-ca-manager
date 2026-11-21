import { useTranslation } from 'react-i18next'
import { Notice } from '../../../components/atelier/Form'
import { hiddenLegacyGroupRows } from './groupMapping'

/** Warns, without blocking, that legacy `groups -> attribute` rows are no longer read. */
export default function LegacyGroupsNotice({ mapping }) {
  const { t } = useTranslation()
  const hidden = hiddenLegacyGroupRows(mapping)
  if (!hidden.length) return null
  return <Notice tone="warn" role="status">{t('sso.legacyGroupsHidden', { attributes: hidden.join(', ') })}</Notice>
}
