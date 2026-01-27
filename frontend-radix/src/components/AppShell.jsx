/**
 * AppShell Component - Main application layout
 */
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function AppShell() {
  const location = useLocation()
  
  // Extract current page from pathname (empty string for dashboard)
  const activePage = location.pathname.split('/')[1] || ''

  return (
    <div className="flex h-screen bg-bg-primary overflow-hidden">
      <Sidebar activePage={activePage} />
      <div className="flex-1 flex overflow-hidden">
        <Outlet />
      </div>
    </div>
  )
}
