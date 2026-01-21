import { Tabs } from '../../components/ui/Tabs';
import { ActivityFeed } from '../../components/domain/ActivityFeed';
import { SearchToolbar } from '../../components/domain/SearchToolbar';
import { getApplicationLogs, getPKIOperations } from '../../services/mockData';
import styles from './ActivityLog.module.css';

/**
 * Activity Log Page
 * 
 * Two tabs:
 * - Application Logs (user actions, system events)
 * - PKI Operations (certificates, CAs, etc.)
 */
export function ActivityLog() {
  const appLogs = getApplicationLogs();
  const pkiOps = getPKIOperations();

  const filters = [
    {
      label: 'Time Range',
      options: ['Last Hour', 'Last 24 Hours', 'Last 7 Days', 'Last 30 Days'],
    },
    {
      label: 'User',
      options: ['All Users', 'admin', 'operator', 'system'],
    },
    {
      label: 'Action Type',
      options: ['All Actions', 'Create', 'Update', 'Delete', 'Login', 'Logout'],
    },
  ];

  const actions = [
    { label: 'Export Logs', icon: 'ph ph-download-simple', variant: 'default' },
    { label: 'Clear Filters', icon: 'ph ph-x', variant: 'default' },
  ];

  return (
    <div className={styles.activityLog}>
      <Tabs>
        <Tabs.List>
          <Tabs.Tab>Application Logs</Tabs.Tab>
          <Tabs.Tab>PKI Operations</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panels>
          {/* Application Logs Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <SearchToolbar
                placeholder="Search application logs..."
                filters={filters}
                actions={actions}
                onSearch={(query) => console.log('Search:', query)}
                onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
              />
              <ActivityFeed items={appLogs} />
            </div>
          </Tabs.Panel>

          {/* PKI Operations Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <SearchToolbar
                placeholder="Search PKI operations..."
                filters={filters}
                actions={actions}
                onSearch={(query) => console.log('Search:', query)}
                onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
              />
              <ActivityFeed items={pkiOps} />
            </div>
          </Tabs.Panel>
        </Tabs.Panels>
      </Tabs>
    </div>
  );
}

export default ActivityLog;
