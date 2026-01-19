/**
 * Main App Layout with Sidebar and Topbar
 */

import { AppShell, Burger, Group, Text, UnstyledButton, Avatar, Menu, ActionIcon, Stack } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconDashboard,
  IconCertificate,
  IconShieldCheck,
  IconKey,
  IconUsers,
  IconSettings,
  IconLogout,
  IconMoon,
  IconSun,
  IconUser,
  IconPalette,
} from '@tabler/icons-react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import type { ReactNode } from 'react';
import classes from './AppLayout.module.css';

interface AppLayoutProps {
  children: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  const [opened, { toggle }] = useDisclosure();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { colorScheme, toggleColorScheme } = useTheme();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const navItems = [
    { icon: IconDashboard, label: 'Dashboard', path: '/dashboard' },
    { icon: IconCertificate, label: 'Certificates', path: '/certificates' },
    { icon: IconShieldCheck, label: 'Certificate Authorities', path: '/cas' },
    { icon: IconKey, label: 'ACME', path: '/acme' },
    { icon: IconKey, label: 'SCEP', path: '/scep' },
    { icon: IconUsers, label: 'Users', path: '/users' },
    { icon: IconSettings, label: 'Settings', path: '/settings' },
  ];

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{
        width: 250,
        breakpoint: 'sm',
        collapsed: { mobile: !opened },
      }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Group gap="xs">
              <IconShieldCheck size={28} color="var(--mantine-color-primary-6)" />
              <Text size="xl" fw={700}>UCM</Text>
            </Group>
          </Group>

          <Group>
            <ActionIcon
              variant="subtle"
              onClick={toggleColorScheme}
              title="Toggle theme"
              size="lg"
            >
              {colorScheme === 'dark' ? <IconSun size={20} /> : <IconMoon size={20} />}
            </ActionIcon>

            <Menu shadow="md" width={200}>
              <Menu.Target>
                <UnstyledButton className={classes.userButton}>
                  <Group>
                    <Avatar color="primary" radius="xl" size="sm">
                      {user?.username?.[0]?.toUpperCase() || 'U'}
                    </Avatar>
                    <div style={{ flex: 1 }}>
                      <Text size="sm" fw={500}>
                        {user?.username || 'User'}
                      </Text>
                      <Text c="dimmed" size="xs">
                        {user?.email || ''}
                      </Text>
                    </div>
                  </Group>
                </UnstyledButton>
              </Menu.Target>

              <Menu.Dropdown>
                <Menu.Label>Account</Menu.Label>
                <Menu.Item
                  leftSection={<IconUser size={16} />}
                  onClick={() => navigate('/profile')}
                >
                  Profile
                </Menu.Item>
                <Menu.Item
                  leftSection={<IconPalette size={16} />}
                  onClick={() => navigate('/theme')}
                >
                  Theme Settings
                </Menu.Item>

                <Menu.Divider />

                <Menu.Item
                  color="red"
                  leftSection={<IconLogout size={16} />}
                  onClick={handleLogout}
                >
                  Logout
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="md">
        <Stack gap="xs">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path || location.pathname.startsWith(item.path + '/');

            return (
              <UnstyledButton
                key={item.path}
                className={classes.navButton}
                data-active={isActive || undefined}
                component={Link}
                to={item.path}
              >
                <Group>
                  <Icon size={20} />
                  <Text size="sm">{item.label}</Text>
                </Group>
              </UnstyledButton>
            );
          })}
        </Stack>
      </AppShell.Navbar>

      <AppShell.Main>{children}</AppShell.Main>
    </AppShell>
  );
}
