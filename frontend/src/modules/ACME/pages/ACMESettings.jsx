import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  TextInput,
  Switch,
  Paper,
  Stack,
  Text,
  Group,
  Select
} from '@mantine/core';
import { FloppyDisk, ArrowLeft } from '@phosphor-icons/react';
import { PageHeader } from '../../../components/ui/Layout';
import { AcmeService } from '../services/acme.service';
import { notifications } from '@mantine/notifications';

const ACMESettings = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState({
    enabled: false,
    provider: 'Built-in',
    contact_email: ''
  });

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const data = await AcmeService.getSettings();
      setSettings(data);
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to load ACME settings',
        color: 'red'
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await AcmeService.updateSettings(settings);
      notifications.show({
        title: 'Success',
        message: 'ACME settings saved',
        color: 'green'
      });
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: 'Failed to save settings',
        color: 'red'
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="ACME Settings" 
        backAction={() => navigate('/acme')}
        actions={
          <Button 
            leftSection={<FloppyDisk size={16} />} 
            size="xs" 
            onClick={handleSave}
            loading={saving}
          >
            Save Changes
          </Button>
        }
      />

      <div style={{ padding: '24px', maxWidth: '800px' }}>
        <Paper p="xl" withBorder>
          <Stack gap="lg">
            <div>
              <Text size="lg" fw={600} mb="xs">General Configuration</Text>
              <Text size="sm" c="dimmed">Configure the Automatic Certificate Management Environment (ACME) server.</Text>
            </div>

            <Group justify="space-between" align="center">
              <div>
                <Text fw={500}>Enable ACME Server</Text>
                <Text size="xs" c="dimmed">Allow clients to request certificates via ACME protocol</Text>
              </div>
              <Switch 
                checked={settings.enabled}
                onChange={(e) => setSettings({...settings, enabled: e.currentTarget.checked})}
              />
            </Group>

            <Select
              label="Provider Mode"
              description="Choose how the ACME server operates"
              data={[
                { value: 'Built-in', label: 'Built-in CA (Direct Issuance)' },
                { value: 'Proxy', label: 'Proxy (Forward to another ACME server)' }
              ]}
              value={settings.provider}
              onChange={(val) => setSettings({...settings, provider: val})}
            />

            <TextInput
              label="Contact Email"
              description="Default contact email for ACME accounts"
              placeholder="admin@example.com"
              value={settings.contact_email || ''}
              onChange={(e) => setSettings({...settings, contact_email: e.currentTarget.value})}
            />
          </Stack>
        </Paper>
      </div>
    </div>
  );
};

export default ACMESettings;
