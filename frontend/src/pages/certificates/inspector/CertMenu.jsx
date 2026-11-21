/**
 * The mockup's certMenu(): « Actions du certificat », the name, then one full-width button per
 * action (copy the name, its activity, revoke in red), and why a revoked certificate offers no
 * renewal. The product's other actions follow the mockup's three, deletion last.
 */
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Icon } from '../../../components/atelier'

/** items: [{ id, icon, label, onClick, danger?, write? }], already filtered by right and state. */
export function CertMenu({ name, items, revoked, onClose }) {
  const { t } = useTranslation()
  return (
    <AtelierDialog title={t('inspector.cert.actionsTitle')} size="narrow" onClose={onClose} testId="inspector-actions-dialog">
      <p className="muted" style={{ marginBottom: 20 }}>{name}</p>
      <div className="columns-list">
        {items.map((a) => (
          <button key={a.id} type="button" className={a.danger ? 'btn danger' : 'btn'} data-action={`cert-${a.id}`}
            data-write={a.write ? '' : undefined} onClick={() => { onClose(); a.onClick?.() }}>
            <Icon name={a.icon} />{a.label}
          </button>
        ))}
      </div>
      {revoked && <p className="small muted" style={{ marginTop: 14 }}>{t('inspector.cert.revokedMenuNote')}</p>}
    </AtelierDialog>
  )
}
