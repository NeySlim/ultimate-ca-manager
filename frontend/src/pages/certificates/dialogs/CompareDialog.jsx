/**
 * The mockup's compare() where no detached window opens (a phone): the ticked certificates, two
 * to four, side by side in its wide dialog, the comparison of the detached window, and « Fermer la
 * comparaison ».
 */
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from '../../../components/atelier'
import { CompareView } from '../compare/CompareView'

export function CompareDialog({ ids, onClose }) {
  const { t } = useTranslation()
  return (
    <AtelierDialog title={t('compare.countTitle', { count: ids.length })} size="wide" onClose={onClose} testId="compare-dialog">
      <CompareView ids={ids} />
      <div className="modal-actions"><button type="button" className="btn primary" data-write="false" data-action="close-modal" onClick={onClose}>{t('compare.close')}</button></div>
    </AtelierDialog>
  )
}

export default CompareDialog
