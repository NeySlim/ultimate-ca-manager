import React, { createContext, useContext, useState } from 'react';

const ViewContext = createContext();

export const useView = () => {
  const context = useContext(ViewContext);
  if (!context) {
    throw new Error('useView must be used within a ViewProvider');
  }
  return context;
};

export const ViewProvider = ({ children }) => {
  const [viewMode, setViewMode] = useState('list'); // 'list' | 'grid'
  
  return (
    <ViewContext.Provider value={{ viewMode, setViewMode }}>
      {children}
    </ViewContext.Provider>
  );
};
