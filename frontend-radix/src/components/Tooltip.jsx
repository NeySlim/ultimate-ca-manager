/**
 * Tooltip Component - Radix Tooltip wrapper
 */
import * as Tooltip from '@radix-ui/react-tooltip'

export function TooltipComponent({ children, content, side = 'top', delayDuration = 200 }) {
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
            className="bg-bg-tertiary border border-border px-3 py-1.5 rounded-lg text-xs text-text-primary shadow-xl z-50 max-w-xs"
          >
            {content}
            <Tooltip.Arrow className="fill-border" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
