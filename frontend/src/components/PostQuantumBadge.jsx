import { useTranslation } from 'react-i18next'
import { Atom } from '@phosphor-icons/react'
import { Badge } from './Badge'
import { isPostQuantum } from '../lib/keyAlgorithms'

/** Badge for a post-quantum key: the API flag, or a label the registry knows as one. */
export function PostQuantumBadge({ postQuantum, algorithm, size = 'sm', className }) {
  const { t } = useTranslation()
  if (!postQuantum && !isPostQuantum(algorithm)) return null
  return (
    <Badge variant="violet" size={size} icon={Atom} className={className} title={t('common.postQuantumHint')}
      data-testid="post-quantum-badge">
      {t('common.postQuantum')}
    </Badge>
  )
}
