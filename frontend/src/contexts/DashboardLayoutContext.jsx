import { createContext, useContext, useState } from 'react';

const DashboardLayoutContext = createContext();

export function DashboardLayoutProvider({ children }) {
  const [isEditMode, setIsEditMode] = useState(false);

  const toggleEditMode = () => setIsEditMode(prev => !prev);
  const exitEditMode = () => setIsEditMode(false);

  return (
    <DashboardLayoutContext.Provider value={{
      isEditMode,
      toggleEditMode,
      exitEditMode,
    }}>
      {children}
    </DashboardLayoutContext.Provider>
  );
}

export function useDashboardLayout() {
  const context = useContext(DashboardLayoutContext);
  if (!context) {
    throw new Error('useDashboardLayout must be used within DashboardLayoutProvider');
  }
  return context;
}
