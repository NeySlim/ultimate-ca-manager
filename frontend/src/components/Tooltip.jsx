/**
 * Tooltip Component - Radix Tooltip wrapper: the mockup's tip, 12 px on the raised surface
 */
import * as Tooltip from '@radix-ui/react-tooltip'
import { Question } from '@phosphor-icons/react'
import { useTranslation } from 'react-i18next'
import { cn } from '../lib/utils'

export function TooltipComponent({ 
  children, 
  content, 
  side = 'top', 
  delayDuration = 400,
  className 
}) {
  return (
    <Tooltip.Provider delayDuration={delayDuration}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          {children}
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            side={side}
            sideOffset={5}
            className={cn('ui-tip', className)}
          >
            {content}
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}

// Helper icon with tooltip - for field labels
export function HelpTooltip({ content, side = 'top' }) {
  const { t } = useTranslation()
  return (
    <TooltipComponent content={content} side={side} delayDuration={300}>
      <button type="button" className="ui-help-tip" aria-label={typeof content === 'string' ? content : t('common.help')}>
        <Question aria-hidden="true" />
      </button>
    </TooltipComponent>
  )
}
