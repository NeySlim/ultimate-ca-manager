/**
 * An empty module that waits on the first-run steps (the mockup's emptyBlock() with emptyAction('setup')):
 * while the steps remain, the way to the assistant; else the page's own next action. Mounted only on an
 * empty page, so the first-run state is read then and not on every visit.
 */
import { useTranslation } from 'react-i18next'
import { EmptyBlock } from '../atelier/EmptyBlock'
import { usePermission } from '../../hooks'
import { useSetup, setupPending, openSetupAction } from './useSetup'

export function SetupEmptyBlock({ action, ...block }) {
  const { t } = useTranslation()
  const { hasPermission } = usePermission()
  const setup = useSetup({ admin: hasPermission('*') })
  return <EmptyBlock {...block} action={setupPending(setup) ? openSetupAction(t) : action} />
}
