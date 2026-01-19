import { Group, Burger, Text, ActionIcon, Menu } from '@mantine/core';
import { 
  Bell, 
  Gear, 
  User, 
  SignOut,
  Palette
} from '@phosphor-icons/react';
import { useAuth } from '../../contexts/AuthContext';

export default function TopBar({ 
  mobileOpened, 
  desktopOpened, 
  toggleMobile, 
  toggleDesktop 
}) {
  const { user, logout } = useAuth();

  return (
    <Group h="100%" px="md" justify="space-between">
      <Group>
        <Burger
          opened={mobileOpened}
          onClick={toggleMobile}
          hiddenFrom="sm"
          size="sm"
        />
        <Burger
          opened={desktopOpened}
          onClick={toggleDesktop}
          visibleFrom="sm"
          size="sm"
        />
        <Text size="15px" fw={600}>UCM</Text>
      </Group>

      <Group gap="xs">
        <ActionIcon variant="subtle" size="lg">
          <Bell size={18} />
        </ActionIcon>
        
        <ActionIcon variant="subtle" size="lg">
          <Palette size={18} />
        </ActionIcon>

        <Menu shadow="md" width={200}>
          <Menu.Target>
            <ActionIcon variant="subtle" size="lg">
              <User size={18} weight="fill" />
            </ActionIcon>
          </Menu.Target>

          <Menu.Dropdown>
            <Menu.Label>{user?.username || 'User'}</Menu.Label>
            <Menu.Item leftSection={<Gear size={14} />}>
              Settings
            </Menu.Item>
            <Menu.Divider />
            <Menu.Item 
              leftSection={<SignOut size={14} />}
              color="red"
              onClick={logout}
            >
              Logout
            </Menu.Item>
          </Menu.Dropdown>
        </Menu>
      </Group>
    </Group>
  );
}
