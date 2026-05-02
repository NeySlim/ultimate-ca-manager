import { useTranslation } from 'react-i18next'
import { Rocket } from '@phosphor-icons/react'
import { DetailHeader, DetailContent, UpdateChecker } from '../../components'

export default function UpdatesSection() {
  const { t } = useTranslation()
  return (
    <DetailContent>
      <DetailHeader
        icon={Rocket}
        title={t('settings.updatesTitle')}
        subtitle={t('settings.updatesSubtitle')}
      />
      <UpdateChecker />
    </DetailContent>
  )
}
