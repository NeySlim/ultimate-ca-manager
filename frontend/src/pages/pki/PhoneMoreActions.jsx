/**
 * On a phone the mockup's page head hides every button but the main one (`.page-head .actions
 * .btn:not(.primary)`): the hidden actions stay reachable from a « ⋯ » button, which opens them in
 * the mockup's certMenu() dialog. Nothing is drawn on a wider screen, where the buttons show.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { IconBtn } from '../../components/atelier'
import { useMobile } from '../../contexts/MobileContext'
import { CertMenu } from '../certificates/inspector/CertMenu'

/** items: [{ id, icon, label, onClick, write?, disabled? }], the page head's buttons other than the main one. */
export function PhoneMoreActions({ title, items }) {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  const [open, setOpen] = useState(false)
  const shown = items.filter((a) => a && !a.disabled)
  if (!isMobile || !shown.length) return null
  return (
    <>
      <IconBtn quiet icon="more" title={false} label={t('atelier.pageActions', { name: title })} data-action="page-actions" onClick={() => setOpen(true)} />
      {open && <CertMenu title={t('atelier.pageActionsTitle')} name={title} items={shown} onClose={() => setOpen(false)} />}
    </>
  )
}

export default PhoneMoreActions
