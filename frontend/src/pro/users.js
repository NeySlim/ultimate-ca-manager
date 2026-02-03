/**
 * Pro Users Extensions
 * Dynamically imported by Users page when Pro module is present
 */
import { UsersThree } from '@phosphor-icons/react'
import GroupsSection from './components/GroupsSection'

// Additional tabs for Users page (Pro)
export const proUsersTabs = [
  { 
    id: 'groups', 
    label: 'Groups', 
    icon: UsersThree, 
    pro: true,
    component: GroupsSection
  },
]
