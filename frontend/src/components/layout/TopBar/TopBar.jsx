import React from 'react';
import { 
  SidebarSimple, 
  House, 
  MagnifyingGlass, 
  Moon, 
  Bell, 
  Gear, 
  CaretDown,
  SquaresFour,
  ListDashes,
  PencilSimple
} from '@phosphor-icons/react';
import { useView } from '../../../core/context/ViewContext';

const TopBar = ({ isSidebarOpen, toggleSidebar, isDetailsOpen, toggleDetails }) => {
  const { viewMode, setViewMode } = useView();

  return (
    <div className="topbar">
      
      {/* 1. LEFT: Logo + Nav */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {/* Logo */}
        <div style={{ 
          display: 'flex', alignItems: 'center', gap: '8px', 
          fontWeight: 700, fontSize: '14px', color: '#c1c2c5', 
          paddingRight: '12px', borderRight: '1px solid #373a40' 
        }}>
          <i className="ph-fill ph-link" style={{ fontSize: '18px', color: '#5a8fc7' }}></i>
          UCM
        </div>

        {/* Sidebar Toggle */}
        <button 
          onClick={toggleSidebar}
          style={{ 
            background: 'none', border: 'none', color: isSidebarOpen ? '#5a8fc7' : '#909296', 
            cursor: 'pointer', display: 'flex' 
          }}
          title="Toggle Sidebar"
        >
          <SidebarSimple size={18} weight={isSidebarOpen ? "fill" : "regular"} />
        </button>

        {/* Breadcrumbs */}
        <div style={{ display: 'flex', alignItems: 'center', fontSize: '13px', fontWeight: 500, color: '#909296' }}>
           <div style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', padding: '2px 4px', borderRadius: '3px' }}>
             <House size={14} style={{ marginRight: '4px' }} /> Home
           </div>
           <span style={{ margin: '0 4px', opacity: 0.4 }}>/</span>
           <div style={{ color: '#c1c2c5' }}>Dashboard</div>
        </div>
      </div>

      {/* 2. CENTER: Command Palette */}
      <div style={{ flex: 1, display: 'flex', justifyContent: 'center', padding: '0 20px' }}>
         <div style={{ 
           width: '100%', maxWidth: '480px', height: '30px', 
           backgroundColor: '#1A1B1E', border: '1px solid #373a40', borderRadius: '3px',
           display: 'flex', alignItems: 'center', padding: '0 8px', color: '#909296', fontSize: '12px'
         }}>
            <MagnifyingGlass size={14} />
            <input 
              type="text" 
              placeholder="Search resources..." 
              style={{ 
                background: 'none', border: 'none', color: 'inherit', flex: 1, 
                marginLeft: '8px', outline: 'none', fontSize: '12px' 
              }} 
            />
            <span style={{ 
              background: '#2c2e33', border: '1px solid #373a40', borderRadius: '2px', 
              padding: '1px 4px', fontSize: '10px', fontFamily: 'JetBrains Mono' 
            }}>Ctrl+K</span>
         </div>
      </div>

      {/* 3. RIGHT: Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        
        {/* View Toggles */}
        <div style={{ display: 'flex', background: '#2c2e33', borderRadius: '3px', padding: '2px', marginRight: '8px' }}>
           <button 
             onClick={() => setViewMode('list')}
             style={{ 
               background: viewMode === 'list' ? '#373a40' : 'none', border: 'none', borderRadius: '2px',
               color: viewMode === 'list' ? '#c1c2c5' : '#909296', cursor: 'pointer', padding: '2px 4px' 
             }}
           >
             <ListDashes size={18} />
           </button>
           <button 
             onClick={() => setViewMode('grid')}
             style={{ 
                background: viewMode === 'grid' ? '#373a40' : 'none', border: 'none', borderRadius: '2px',
                color: viewMode === 'grid' ? '#c1c2c5' : '#909296', cursor: 'pointer', padding: '2px 4px' 
             }}
           >
             <SquaresFour size={18} />
           </button>
        </div>

        {/* Layout Edit */}
        <button style={{ 
            background: 'none', border: '1px solid #373a40', color: '#909296', borderRadius: '3px', 
            padding: '4px 10px', fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', marginRight: '8px'
        }}>
            <PencilSimple size={14} /> Edit Layout
        </button>

        <div style={{ width: '1px', height: '20px', backgroundColor: '#373a40', margin: '0 4px' }}></div>

        <button style={{ background: 'none', border: 'none', color: '#909296', cursor: 'pointer' }}>
           <SidebarSimple size={18} weight={isDetailsOpen ? "fill" : "regular"} style={{ transform: 'rotate(180deg)' }} onClick={toggleDetails} />
        </button>
        
        <button style={{ background: 'none', border: 'none', color: '#909296', cursor: 'pointer' }}>
           <Moon size={18} />
        </button>

        <button style={{ background: 'none', border: 'none', color: '#909296', cursor: 'pointer' }}>
           <Bell size={18} />
        </button>

        <button style={{ background: 'none', border: 'none', color: '#909296', cursor: 'pointer' }}>
           <Gear size={18} />
        </button>

        <div style={{ width: '1px', height: '20px', backgroundColor: '#373a40', margin: '0 4px' }}></div>

        {/* User Profile */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', padding: '2px 4px', borderRadius: '3px' }}>
           <div style={{ 
             width: '24px', height: '24px', background: 'linear-gradient(135deg, #5a8fc7, #7aa5d9)', 
             borderRadius: '3px', display: 'flex', alignItems: 'center', justifyContent: 'center', 
             fontSize: '11px', fontWeight: 600, color: 'white' 
           }}>AD</div>
           <div style={{ fontSize: '13px', fontWeight: 500, color: '#c1c2c5' }}>Admin</div>
           <CaretDown size={12} color="#909296" />
        </div>

      </div>
    </div>
  );
};

export default TopBar;
