/**
 * Empty state of any page: the empty block of the list template (icon, why, next action).
 * Kept for its callers; new code can use EmptyBlock from components/list directly.
 */
import { FileX } from '@phosphor-icons/react'
import { EmptyBlock } from './list/StateBlocks'

export function EmptyState({ icon = FileX, title = 'No data', description, action }) {
  return <EmptyBlock icon={icon} title={title} description={description} action={action} />
}
