import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { House, Certificate, ShieldCheck, Globe, Users, WarningCircle, CheckCircle, Clock } from '@phosphor-icons/react';
import { Stack, Group, Card, Text, Button, Loader, Badge } from '../../../components/ui';
import { dashboardService } from '../services/dashboard.service';
import './DashboardPage.css';

const StatCard = ({ icon, label, value, trend, loading }) => (
  <Card className="stat-card">
    <div className="stat-icon">{icon}</div>
    <div className="stat-content">
      <Text className="stat-label">{label}</Text>
      {loading ? (
        <Loader size="sm" />
      ) : (
        <>
          <Text className="stat-value">{value || '0'}</Text>
          {trend && (
            <Text className={`stat-trend ${trend.isPositive ? 'positive' : 'negative'}`}>
              {trend.isPositive ? '+' : ''}{trend.value}
            </Text>
          )}
        </>
      )}
    </div>
  </Card>
);

const DashboardPage = () => {
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [activity, setActivity] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setLoading(true);
      const [statsData, activityData] = await Promise.all([
        dashboardService.getStats(),
        dashboardService.getRecentActivity({ limit: 10 })
      ]);
      setStats(statsData || {});
      setActivity(activityData?.activity || []);
    } catch (error) {
      console.error('Failed to load dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dashboard-page">
      {/* Page Header */}
      <div className="page-header">
        <Group>
          <House size={24} weight="duotone" className="icon-gradient" />
          <div>
            <h1 className="page-title">Dashboard</h1>
            <Text className="page-subtitle">System Overview & Recent Activity</Text>
          </div>
        </Group>
        <Button variant="primary" onClick={() => loadDashboard()}>
          Refresh
        </Button>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        <StatCard
          icon={<ShieldCheck size={32} weight="duotone" className="icon-gradient" />}
          label="Certificate Authorities"
          value={stats.cas_count}
          loading={loading}
        />
        <StatCard
          icon={<Certificate size={32} weight="duotone" className="icon-gradient" />}
          label="Total Certificates"
          value={stats.certs_count}
          loading={loading}
        />
        <StatCard
          icon={<WarningCircle size={32} weight="duotone" style={{ color: 'var(--status-warning)' }} />}
          label="Expiring Soon"
          value={stats.expiring_count}
          loading={loading}
        />
        <StatCard
          icon={<Globe size={32} weight="duotone" className="icon-gradient" />}
          label="ACME Orders"
          value={stats.acme_orders_count}
          loading={loading}
        />
      </div>

      {/* Main Content Grid */}
      <div className="dashboard-grid">
        {/* Recent Activity */}
        <Card className="dashboard-card">
          <div className="card-header-custom">
            <h3 className="card-title">Recent Activity</h3>
            <Button size="sm" onClick={() => navigate('/audit')}>View All</Button>
          </div>
          <Stack className="activity-list">
            {loading ? (
              <div className="loading-center"><Loader /></div>
            ) : activity.length === 0 ? (
              <Text className="empty-state">No recent activity</Text>
            ) : (
              activity.map((item, idx) => (
                <div key={idx} className="activity-item">
                  <div className="activity-icon">
                    {item.type === 'cert_issued' && <CheckCircle size={20} weight="fill" style={{ color: 'var(--status-success)' }} />}
                    {item.type === 'cert_revoked' && <WarningCircle size={20} weight="fill" style={{ color: 'var(--status-error)' }} />}
                    {item.type === 'ca_created' && <ShieldCheck size={20} weight="fill" style={{ color: 'var(--status-info)' }} />}
                  </div>
                  <div className="activity-content">
                    <Text className="activity-title">{item.description}</Text>
                    <Text className="activity-time">{item.timestamp}</Text>
                  </div>
                </div>
              ))
            )}
          </Stack>
        </Card>

        {/* System Status */}
        <Card className="dashboard-card">
          <div className="card-header-custom">
            <h3 className="card-title">System Status</h3>
          </div>
          <Stack>
            <div className="status-item">
              <Group>
                <div className="status-dot online"></div>
                <Text>UCM Core</Text>
              </Group>
              <Badge variant="active">Online</Badge>
            </div>
            <div className="status-item">
              <Group>
                <div className="status-dot online"></div>
                <Text>Database</Text>
              </Group>
              <Badge variant="active">Operational</Badge>
            </div>
            <div className="status-item">
              <Group>
                <div className="status-dot online"></div>
                <Text>ACME Service</Text>
              </Group>
              <Badge variant="active">Running</Badge>
            </div>
            <div className="status-item">
              <Group>
                <div className="status-dot online"></div>
                <Text>SCEP Service</Text>
              </Group>
              <Badge variant="active">Running</Badge>
            </div>
          </Stack>
        </Card>
      </div>
    </div>
  );
};

export default DashboardPage;
