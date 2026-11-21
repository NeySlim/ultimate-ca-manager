import { useTranslation } from 'react-i18next'
import { Icon } from '../../components/atelier'

/** The mockup's yesNo(): a flag with its icon, so the colour is never the only signal. */
export function YesNo({ value }) {
  const { t } = useTranslation()
  return value
    ? <span className="flag"><Icon name="check" />{t('common.yes')}</span>
    : <span className="flag muted"><Icon name="block" />{t('common.no')}</span>
}

export default YesNo
