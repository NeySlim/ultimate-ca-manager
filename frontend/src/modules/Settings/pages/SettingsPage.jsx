import React, { useState } from 'react';
import { Button, Tabs } from '@mantine/core';
import { PenNib } from '@phosphor-icons/react';
import { PageHeader, Grid, Widget } from '../../../components/ui/Layout';
import GeneralTab from '../components/GeneralTab';
import SecurityTab from '../components/SecurityTab';
import DatabaseTab from '../components/DatabaseTab';
import './SettingsPage.css';

const SettingsPage = () => {
  return (
    <div className="settings-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="System Settings" 
        actions={
          <Button leftSection={<PenNib size={16} />} size="xs">
            Edit Global Config
          </Button>
        }
      />

      <div style={{ flex: 1, padding: '16px', overflowY: 'auto' }}>
        <Tabs defaultValue="general">
            <Tabs.List mb="lg">
                <Tabs.Tab value="general">General</Tabs.Tab>
                <Tabs.Tab value="security">Security</Tabs.Tab>
                <Tabs.Tab value="database">Database</Tabs.Tab>
                <Tabs.Tab value="advanced">Advanced</Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="general">
                <GeneralTab />
            </Tabs.Panel>
            
            <Tabs.Panel value="security">
                <SecurityTab />
            </Tabs.Panel>
            
            <Tabs.Panel value="database">
                <DatabaseTab />
            </Tabs.Panel>
            
            <Tabs.Panel value="advanced">
                <div style={{ padding: 40, textAlign: 'center', color: 'gray' }}>
                    Advanced settings coming soon
                </div>
            </Tabs.Panel>
        </Tabs>
      </div>
    </div>
  );
};

export default SettingsPage;
