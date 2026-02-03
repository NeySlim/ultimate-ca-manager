/**
 * Pro Settings Extensions
 * Dynamically imported by Settings page when Pro module is present
 */
import { Key } from '@phosphor-icons/react'
import SSOSettingsSection from './components/SSOSettingsSection'

// Additional settings categories for Pro
export const proSettingsCategories = [
  { 
    id: 'sso', 
    label: 'SSO', 
    icon: Key, 
    description: 'Single Sign-On providers',
    pro: true,
    component: SSOSettingsSection
  },
]
