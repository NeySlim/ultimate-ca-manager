/**
 * Settings Page
 */

import { useState, useEffect } from 'react';
import { Tabs, Stack, TextInput, Button, Group, Text, Switch, Card, PasswordInput, Select } from '@mantine/core';
import { IconSettings, IconMail, IconDatabase, IconShield, IconBell } from '@tabler/icons-react';
import { api } from '../utils/api';

export function SettingsPage() {
  const [settings, setSettings] = useState<any>({});

  const loadSettings = async () => {
    try {
      const data = await api.settings.getGeneral();
      setSettings(data);
    } catch (error: any) {
      console.error('Failed to load settings:', error);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleSaveGeneral = async () => {
    try {
      await api.settings.updateGeneral(settings);
      alert('Settings saved successfully');
    } catch (error: any) {
      alert('Failed to save settings');
    }
  };

  return (
    <Stack gap="md">
      <Text size="xl" fw={700}>Settings</Text>

      <Tabs defaultValue="general">
        <Tabs.List>
          <Tabs.Tab value="general" leftSection={<IconSettings size={16} />}>
            General
          </Tabs.Tab>
          <Tabs.Tab value="email" leftSection={<IconMail size={16} />}>
            Email
          </Tabs.Tab>
          <Tabs.Tab value="backup" leftSection={<IconDatabase size={16} />}>
            Backup
          </Tabs.Tab>
          <Tabs.Tab value="security" leftSection={<IconShield size={16} />}>
            Security
          </Tabs.Tab>
          <Tabs.Tab value="notifications" leftSection={<IconBell size={16} />}>
            Notifications
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="general" pt="md">
          <Card withBorder>
            <Stack gap="md">
              <TextInput
                label="Organization Name"
                value={settings.organization_name || ''}
                onChange={(e) => setSettings({ ...settings, organization_name: e.target.value })}
              />
              <TextInput
                label="Admin Email"
                type="email"
                value={settings.admin_email || ''}
                onChange={(e) => setSettings({ ...settings, admin_email: e.target.value })}
              />
              <Switch
                label="Enable User Registration"
                checked={settings.enable_registration || false}
                onChange={(e) => setSettings({ ...settings, enable_registration: e.target.checked })}
              />
              <Switch
                label="Require Email Verification"
                checked={settings.require_email_verification || false}
                onChange={(e) => setSettings({ ...settings, require_email_verification: e.target.checked })}
              />
              <Group justify="flex-end">
                <Button onClick={handleSaveGeneral}>Save Changes</Button>
              </Group>
            </Stack>
          </Card>
        </Tabs.Panel>

        <Tabs.Panel value="email" pt="md">
          <Card withBorder>
            <Stack gap="md">
              <TextInput
                label="SMTP Host"
                placeholder="smtp.example.com"
                value={settings.smtp_host || ''}
                onChange={(e) => setSettings({ ...settings, smtp_host: e.target.value })}
              />
              <TextInput
                label="SMTP Port"
                type="number"
                placeholder="587"
                value={settings.smtp_port || ''}
                onChange={(e) => setSettings({ ...settings, smtp_port: e.target.value })}
              />
              <TextInput
                label="SMTP Username"
                value={settings.smtp_username || ''}
                onChange={(e) => setSettings({ ...settings, smtp_username: e.target.value })}
              />
              <PasswordInput
                label="SMTP Password"
                value={settings.smtp_password || ''}
                onChange={(e) => setSettings({ ...settings, smtp_password: e.target.value })}
              />
              <Switch
                label="Use TLS"
                checked={settings.smtp_use_tls || false}
                onChange={(e) => setSettings({ ...settings, smtp_use_tls: e.target.checked })}
              />
              <Group justify="flex-end">
                <Button variant="light">Test Connection</Button>
                <Button onClick={handleSaveGeneral}>Save Changes</Button>
              </Group>
            </Stack>
          </Card>
        </Tabs.Panel>

        <Tabs.Panel value="backup" pt="md">
          <Card withBorder>
            <Stack gap="md">
              <Text size="sm" fw={600}>Automatic Backup</Text>
              <Switch
                label="Enable Automatic Backup"
                checked={settings.enable_auto_backup || false}
                onChange={(e) => setSettings({ ...settings, enable_auto_backup: e.target.checked })}
              />
              <Select
                label="Backup Frequency"
                data={[
                  { value: 'daily', label: 'Daily' },
                  { value: 'weekly', label: 'Weekly' },
                  { value: 'monthly', label: 'Monthly' }
                ]}
                value={settings.backup_frequency || 'daily'}
                onChange={(value) => setSettings({ ...settings, backup_frequency: value })}
              />
              <TextInput
                label="Retention Days"
                type="number"
                placeholder="30"
                value={settings.backup_retention_days || ''}
                onChange={(e) => setSettings({ ...settings, backup_retention_days: e.target.value })}
              />
              <Group justify="space-between" mt="md">
                <Button variant="light">Backup Now</Button>
                <Button onClick={handleSaveGeneral}>Save Changes</Button>
              </Group>
            </Stack>
          </Card>
        </Tabs.Panel>

        <Tabs.Panel value="security" pt="md">
          <Card withBorder>
            <Stack gap="md">
              <Switch
                label="Require 2FA for Admin"
                checked={settings.require_2fa_admin || false}
                onChange={(e) => setSettings({ ...settings, require_2fa_admin: e.target.checked })}
              />
              <Switch
                label="Enable mTLS Authentication"
                checked={settings.enable_mtls || false}
                onChange={(e) => setSettings({ ...settings, enable_mtls: e.target.checked })}
              />
              <Switch
                label="Enable WebAuthn"
                checked={settings.enable_webauthn || false}
                onChange={(e) => setSettings({ ...settings, enable_webauthn: e.target.checked })}
              />
              <TextInput
                label="Session Timeout (minutes)"
                type="number"
                placeholder="30"
                value={settings.session_timeout || ''}
                onChange={(e) => setSettings({ ...settings, session_timeout: e.target.value })}
              />
              <Group justify="flex-end">
                <Button onClick={handleSaveGeneral}>Save Changes</Button>
              </Group>
            </Stack>
          </Card>
        </Tabs.Panel>

        <Tabs.Panel value="notifications" pt="md">
          <Card withBorder>
            <Stack gap="md">
              <Switch
                label="Certificate Expiry Notifications"
                checked={settings.notify_cert_expiry || false}
                onChange={(e) => setSettings({ ...settings, notify_cert_expiry: e.target.checked })}
              />
              <TextInput
                label="Notify Before Expiry (days)"
                type="number"
                placeholder="30"
                value={settings.notify_before_expiry_days || ''}
                onChange={(e) => setSettings({ ...settings, notify_before_expiry_days: e.target.value })}
              />
              <Switch
                label="Webhook Notifications"
                checked={settings.enable_webhooks || false}
                onChange={(e) => setSettings({ ...settings, enable_webhooks: e.target.checked })}
              />
              <Group justify="flex-end">
                <Button onClick={handleSaveGeneral}>Save Changes</Button>
              </Group>
            </Stack>
          </Card>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
