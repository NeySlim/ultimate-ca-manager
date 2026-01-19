import { Box, Text, Stack, SimpleGrid, Paper, Group } from '@mantine/core';
import { 
  Certificate, 
  Seal, 
  CheckCircle, 
  XCircle 
} from '@phosphor-icons/react';

export default function DashboardPage() {
  const stats = [
    { 
      label: 'Total Certificates', 
      value: '0', 
      icon: Certificate,
      color: '#5a8fc7'
    },
    { 
      label: 'Active CAs', 
      value: '0', 
      icon: Seal,
      color: '#5eb89b'
    },
    { 
      label: 'Valid', 
      value: '0', 
      icon: CheckCircle,
      color: '#81c784'
    },
    { 
      label: 'Expired', 
      value: '0', 
      icon: XCircle,
      color: '#e57373'
    }
  ];

  return (
    <Stack gap="lg">
      <div>
        <Text size="24px" fw={600}>Dashboard</Text>
        <Text size="13px" c="dimmed">Certificate management overview</Text>
      </div>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Paper
              key={stat.label}
              p="md"
              radius="sm"
              withBorder
              style={{
                background: '#2a2a2a',
                borderColor: '#3a3a3a'
              }}
            >
              <Group justify="space-between">
                <div>
                  <Text size="11px" c="dimmed" tt="uppercase" fw={500}>
                    {stat.label}
                  </Text>
                  <Text size="28px" fw={700} mt="xs">
                    {stat.value}
                  </Text>
                </div>
                <Icon 
                  size={40} 
                  weight="duotone"
                  style={{ color: stat.color, opacity: 0.6 }}
                />
              </Group>
            </Paper>
          );
        })}
      </SimpleGrid>

      <Paper
        p="lg"
        radius="sm"
        withBorder
        style={{
          background: '#2a2a2a',
          borderColor: '#3a3a3a'
        }}
      >
        <Text size="15px" fw={600} mb="md">Recent Activity</Text>
        <Text size="13px" c="dimmed">
          No recent activity
        </Text>
      </Paper>
    </Stack>
  );
}
