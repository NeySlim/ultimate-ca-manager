/**
 * Settings Categories
 * All settings now available in community edition
 */
import { Key } from '@phosphor-icons/react'
import SSOSettingsSection from './components/SSOSettingsSection'

// Additional settings categories (formerly Pro)
export const advancedSettingsCategories = [
  { 
    id: 'sso', 
    label: 'SSO', 
    icon: Key, 
    description: 'Single Sign-On providers',
    component: SSOSettingsSection
  },
]
