import { useState } from 'react';
import { 
  Stack, 
  Tabs, 
  Paper, 
  TextInput, 
  Button, 
  Switch,
  Text,
  Group,
  PasswordInput,
  NumberInput
} from '@mantine/core';
import {
  Gear,
  Database,
  Envelope,
  ShieldCheck,
  CloudArrowDown
} from '@phosphor-icons/react';
import { notifications } from '@mantine/notifications';

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('general');

  const handleSave = () => {
    notifications.show({
      title: 'Settings Saved',
      message: 'Your settings have been saved successfully',
      color: 'green'
    });
  };

  return (
    <Stack gap="lg">
      <div>
        <Text size="24px" fw={600}>Settings</Text>
        <Text size="13px" c="dimmed">Configure system settings</Text>
      </div>

      <Tabs value={activeTab} onChange={setActiveTab}>
        <Tabs.List>
          <Tabs.Tab value="general" leftSection={<Gear size={16} />}>
            General
          </Tabs.Tab>
          <Tabs.Tab value="database" leftSection={<Database size={16} />}>
            Database
          </Tabs.Tab>
          <Tabs.Tab value="email" leftSection={<Envelope size={16} />}>
            Email
          </Tabs.Tab>
          <Tabs.Tab value="security" leftSection={<ShieldCheck size={16} />}>
            Security
          </Tabs.Tab>
          <Tabs.Tab value="backup" leftSection={<CloudArrowDown size={16} />}>
            Backup
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="general" pt="lg">
          <Paper p="lg" radius="sm" withBorder style={{ background: '#2a2a2a', borderColor: '#3a3a3a' }}>
            <Stack gap="md">
              <TextInput
                label="System Name"
                description="Display name for this UCM instance"
                placeholder="UCM Production"
              />
              
              <Switch
                label="Enable Auto-Renewal"
                description="Automatically renew certificates before expiration"
              />

              <NumberInput
                label="Certificate Validity (days)"
                description="Default validity period for new certificates"
                defaultValue={365}
                min={1}
                max={3650}
              />

              <Group justify="flex-end" mt="md">
                <Button variant="default">Cancel</Button>
                <Button onClick={handleSave} style={{ background: 'linear-gradient(135deg, #5a8fc7, #7aa5d9)' }}>
                  Save Changes
                </Button>
              </Group>
            </Stack>
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="database" pt="lg">
          <Paper p="lg" radius="sm" withBorder style={{ background: '#2a2a2a', borderColor: '#3a3a3a' }}>
            <Stack gap="md">
              <TextInput
                label="Database Path"
                description="Path to SQLite database file"
                defaultValue="/var/lib/ucm/ucm.db"
                readOnly
              />

              <Switch
                label="Enable Auto-Backup"
                description="Automatically backup database daily"
              />

              <Group justify="flex-end" mt="md">
                <Button variant="default">Vacuum Database</Button>
                <Button onClick={handleSave} style={{ background: 'linear-gradient(135deg, #5a8fc7, #7aa5d9)' }}>
                  Save Changes
                </Button>
              </Group>
            </Stack>
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="email" pt="lg">
          <Paper p="lg" radius="sm" withBorder style={{ background: '#2a2a2a', borderColor: '#3a3a3a' }}>
            <Stack gap="md">
              <TextInput
                label="SMTP Server"
                placeholder="smtp.example.com"
              />

              <NumberInput
                label="SMTP Port"
                defaultValue={587}
              />

              <TextInput
                label="Username"
                placeholder="noreply@example.com"
              />

              <PasswordInput
                label="Password"
                placeholder="••••••••"
              />

              <Switch
                label="Enable TLS"
                description="Use TLS encryption for SMTP connection"
                defaultChecked
              />

              <Group justify="flex-end" mt="md">
                <Button variant="default">Test Connection</Button>
                <Button onClick={handleSave} style={{ background: 'linear-gradient(135deg, #5a8fc7, #7aa5d9)' }}>
                  Save Changes
                </Button>
              </Group>
            </Stack>
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="security" pt="lg">
          <Paper p="lg" radius="sm" withBorder style={{ background: '#2a2a2a', borderColor: '#3a3a3a' }}>
            <Stack gap="md">
              <Switch
                label="Enable mTLS"
                description="Require client certificates for authentication"
              />

              <Switch
                label="Enable WebAuthn"
                description="Allow FIDO2/WebAuthn authentication"
              />

              <NumberInput
                label="Session Timeout (minutes)"
                defaultValue={30}
                min={5}
                max={1440}
              />

              <Group justify="flex-end" mt="md">
                <Button variant="default">Cancel</Button>
                <Button onClick={handleSave} style={{ background: 'linear-gradient(135deg, #5a8fc7, #7aa5d9)' }}>
                  Save Changes
                </Button>
              </Group>
            </Stack>
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="backup" pt="lg">
          <Paper p="lg" radius="sm" withBorder style={{ background: '#2a2a2a', borderColor: '#3a3a3a' }}>
            <Stack gap="md">
              <TextInput
                label="Backup Directory"
                placeholder="/var/lib/ucm/backups"
              />

              <Switch
                label="Enable Scheduled Backups"
                description="Automatically backup system on schedule"
              />

              <NumberInput
                label="Retention Days"
                description="Days to keep old backups"
                defaultValue={30}
                min={1}
                max={365}
              />

              <Group justify="flex-end" mt="md">
                <Button variant="default">Backup Now</Button>
                <Button onClick={handleSave} style={{ background: 'linear-gradient(135deg, #5a8fc7, #7aa5d9)' }}>
                  Save Changes
                </Button>
              </Group>
            </Stack>
          </Paper>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
