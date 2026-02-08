/**
 * Settings Categories
 * All settings now available
 */
import { Key } from '@phosphor-icons/react'
import SSOSettingsSection from './components/SSOSettingsSection'

// Additional settings categories
export const advancedSettingsCategories = [
  { 
    id: 'sso', 
    labelKey: 'settings.tabs.sso', 
    icon: Key, 
    color: 'icon-bg-purple',
    component: SSOSettingsSection
  },
]
