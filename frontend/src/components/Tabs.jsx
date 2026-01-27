/**
 * Tabs Component - Radix Tabs wrapper
 */
import * as Tabs from '@radix-ui/react-tabs'
import { cn } from '../lib/utils'

export function TabsComponent({ tabs, defaultTab, className, children }) {
  return (
    <Tabs.Root defaultValue={defaultTab || tabs[0]?.id} className={cn("flex flex-col", className)}>
      <Tabs.List className="flex gap-1 border-b border-border">
        {tabs.map(tab => (
          <Tabs.Trigger
            key={tab.id}
            value={tab.id}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors relative",
              "text-text-secondary hover:text-text-primary",
              "data-[state=active]:text-accent-primary",
              "focus:outline-none"
            )}
          >
            {tab.icon && <span className="flex-shrink-0">{tab.icon}</span>}
            <span>{tab.label}</span>
            <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent-primary opacity-0 data-[state=active]:opacity-100 transition-opacity" />
          </Tabs.Trigger>
        ))}
      </Tabs.List>

      {tabs.map(tab => (
        <Tabs.Content 
          key={tab.id} 
          value={tab.id}
          className="flex-1 py-4 px-4 focus:outline-none"
        >
          {tab.content}
        </Tabs.Content>
      ))}
    </Tabs.Root>
  )
}
