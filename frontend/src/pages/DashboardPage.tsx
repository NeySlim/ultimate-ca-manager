/**
 * Dashboard Page (placeholder)
 */

import { Container, Title, Text, Paper, SimpleGrid, Stack } from '@mantine/core';
import { IconCertificate, IconShieldCheck, IconKey, IconUsers } from '@tabler/icons-react';
import { useAuth } from '../contexts/AuthContext';

export function DashboardPage() {
  const { user } = useAuth();

  return (
    <Container size="xl" py="xl">
      <Stack gap="xl">
        <div>
          <Title order={1}>Dashboard</Title>
          <Text c="dimmed">Welcome back, {user?.username}!</Text>
        </div>

        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="lg">
          <Paper shadow="sm" p="md" radius="md" withBorder>
            <Stack gap="xs">
              <IconCertificate size={32} color="var(--mantine-color-primary-6)" />
              <Text fw={500} size="lg">0</Text>
              <Text c="dimmed" size="sm">Certificates</Text>
            </Stack>
          </Paper>

          <Paper shadow="sm" p="md" radius="md" withBorder>
            <Stack gap="xs">
              <IconShieldCheck size={32} color="var(--mantine-color-green-6)" />
              <Text fw={500} size="lg">0</Text>
              <Text c="dimmed" size="sm">Certificate Authorities</Text>
            </Stack>
          </Paper>

          <Paper shadow="sm" p="md" radius="md" withBorder>
            <Stack gap="xs">
              <IconKey size={32} color="var(--mantine-color-blue-6)" />
              <Text fw={500} size="lg">0</Text>
              <Text c="dimmed" size="sm">API Keys</Text>
            </Stack>
          </Paper>

          <Paper shadow="sm" p="md" radius="md" withBorder>
            <Stack gap="xs">
              <IconUsers size={32} color="var(--mantine-color-orange-6)" />
              <Text fw={500} size="lg">0</Text>
              <Text c="dimmed" size="sm">Users</Text>
            </Stack>
          </Paper>
        </SimpleGrid>

        <Paper shadow="sm" p="xl" radius="md" withBorder>
          <Text c="dimmed" ta="center">
            Dashboard content coming soon...
          </Text>
        </Paper>
      </Stack>
    </Container>
  );
}
