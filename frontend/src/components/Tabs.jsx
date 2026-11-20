/**
 * Tabs Component - Radix Tabs wrapper drawn as the mockup's detail tabs (12 px, accent underline)
 */
import * as Tabs from '@radix-ui/react-tabs'
import { cn } from '../lib/utils'

export function TabsComponent({ tabs, defaultTab, className, children }) {
  return (
    <Tabs.Root defaultValue={defaultTab || tabs[0]?.id} className={cn("flex flex-col", className)}>
      <Tabs.List className="ui-tabs-list">
        {tabs.map(tab => (
          <Tabs.Trigger
            key={tab.id}
            value={tab.id}
            className="ui-tab"
          >
            {tab.icon && <span className="flex-shrink-0" aria-hidden="true">{tab.icon}</span>}
            <span>{tab.label}</span>
          </Tabs.Trigger>
        ))}
      </Tabs.List>

      {tabs.map(tab => (
        <Tabs.Content 
          key={tab.id} 
          value={tab.id}
          className="ui-tab-panel"
        >
          {tab.content}
        </Tabs.Content>
      ))}
    </Tabs.Root>
  )
}
