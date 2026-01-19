import { Stack, NavLink, Text, Box } from '@mantine/core';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  ChartPie,
  Certificate,
  Seal,
  Folders,
  Gear,
  Users,
  ShieldCheck,
  Key,
  CloudArrowDown
} from '@phosphor-icons/react';

const navItems = [
  { 
    label: 'Dashboard', 
    icon: ChartPie, 
    path: '/dashboard' 
  },
  { 
    label: 'Certificates', 
    icon: Certificate, 
    path: '/certificates' 
  },
  { 
    label: 'Certificate Authorities', 
    icon: Seal, 
    path: '/cas' 
  },
  { 
    label: 'ACME', 
    icon: ShieldCheck, 
    path: '/acme' 
  },
  { 
    label: 'SCEP', 
    icon: Key, 
    path: '/scep' 
  },
  { 
    label: 'Import', 
    icon: CloudArrowDown, 
    path: '/import' 
  },
  { 
    label: 'Users', 
    icon: Users, 
    path: '/users' 
  },
  { 
    label: 'Settings', 
    icon: Gear, 
    path: '/settings' 
  }
];

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <Stack gap={0}>
      {navItems.map((item) => {
        const Icon = item.icon;
        const isActive = location.pathname === item.path;
        
        return (
          <NavLink
            key={item.path}
            label={
              <Text size="13px" fw={500}>
                {item.label}
              </Text>
            }
            leftSection={
              <Icon 
                size={18} 
                weight={isActive ? 'fill' : 'regular'}
                className={isActive ? 'icon-gradient' : ''}
                style={isActive ? {
                  '--accent-start': '#5a8fc7',
                  '--accent-end': '#7aa5d9'
                } : {}}
              />
            }
            active={isActive}
            onClick={() => navigate(item.path)}
            styles={{
              root: {
                borderRadius: '3px',
                padding: '8px 12px',
                marginBottom: '2px',
                '&[data-active]': {
                  background: '#2a2a2a',
                  '&:hover': {
                    background: '#2a2a2a'
                  }
                }
              }
            }}
          />
        );
      })}
    </Stack>
  );
}
