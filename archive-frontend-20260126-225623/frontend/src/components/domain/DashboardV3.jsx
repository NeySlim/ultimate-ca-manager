import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Certificate, 
  Clock, 
  FileText, 
  Globe, 
  Users, 
  ShieldCheck,
  Gear,
  TrendUp,
  Warning,
  CheckCircle,
  Info
} from '@phosphor-icons/react';
import { AreaChart, Area, ResponsiveContainer, Tooltip } from 'recharts';

// Design System V3 Components
import { Card } from '../../design-system/components/primitives/Card';
import { GlassCard } from '../../design-system/components/primitives/GlassCard';
import { Badge } from '../../design-system/components/primitives/Badge';
import { GradientBadge } from '../../design-system/components/primitives/GradientBadge';
import { Button } from '../../design-system/components/primitives/Button';
import { Grid } from '../../design-system/components/layout/Grid';
import { Stack } from '../../design-system/components/layout/Stack';
import { Inline } from '../../design-system/components/layout/Inline';
import { Divider } from '../../design-system/components/layout/Divider';
import { Alert } from '../../design-system/components/feedback/Alert';
import { EmptyState } from '../../design-system/components/feedback/EmptyState';
import { Skeleton } from '../../design-system/components/feedback/Skeleton';
import { useDashboardStats, useDashboardOverview, useDashboardActivity, useDashboardExpiringCerts } from '../../hooks/useDashboard';
import styles from './DashboardV3.module.css';

// Animated Counter Component
function AnimatedCounter({ value, duration = 1200 }) {
  const [count, setCount] = useState(0);
  
  useState(() => {
    const start = 0;
    const end = parseInt(value) || 0;
    const increment = end / (duration / 16);
    let current = start;
    
    const timer = setInterval(() => {
      current += increment;
      if (current >= end) {
        setCount(end);
        clearInterval(timer);
      } else {
        setCount(Math.floor(current));
      }
    }, 16);
    
    return () => clearInterval(timer);
  }, [value, duration]);
  
  return <span>{count.toLocaleString()}</span>;
}

// Stat Card with Gradient Icon
function StatCardV3({ icon: Icon, value, label, sublabel, trend, variant = 'primary', onClick }) {
  const gradientMap = {
    primary: 'linear-gradient(135deg, var(--color-primary-500) 0%, var(--color-primary-600) 100%)',
    success: 'linear-gradient(135deg, var(--color-success-500) 0%, var(--color-success-600) 100%)',
    warning: 'linear-gradient(135deg, var(--color-warning-500) 0%, var(--color-warning-600) 100%)',
    info: 'linear-gradient(135deg, var(--color-info-500) 0%, var(--color-info-600) 100%)',
  };

  return (
    <Card 
      hoverable 
      className={styles.statCard}
      onClick={onClick}
      style={{ cursor: onClick ? 'pointer' : 'default' }}
    >
      <div className={styles.statCardContent}>
        <div className={styles.statCardIcon} style={{ background: gradientMap[variant] }}>
          <Icon size={24} weight="bold" color="white" />
        </div>
        <div className={styles.statCardData}>
          <div className={styles.statCardValue}>
            <AnimatedCounter value={value} />
          </div>
          <div className={styles.statCardLabel}>{label}</div>
          {sublabel && <div className={styles.statCardSublabel}>{sublabel}</div>}
          {trend && (
            <div className={styles.statCardTrend} data-positive={trend.positive}>
              <TrendUp size={14} weight="bold" />
              <span>{trend.text}</span>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

// Quick Action Card
function QuickActionCard({ icon: Icon, title, description, onClick, gradient }) {
  return (
    <Card hoverable onClick={onClick} className={styles.quickAction}>
      <div className={styles.quickActionContent}>
        <div className={styles.quickActionIcon} style={{ background: gradient }}>
          <Icon size={28} weight="bold" color="white" />
        </div>
        <div>
          <div className={styles.quickActionTitle}>{title}</div>
          <div className={styles.quickActionDesc}>{description}</div>
        </div>
      </div>
    </Card>
  );
}

// Activity Timeline Item
function ActivityItem({ type, message, timestamp, user }) {
  const iconMap = {
    created: <Certificate size={16} weight="fill" />,
    revoked: <Warning size={16} weight="fill" />,
    renewed: <CheckCircle size={16} weight="fill" />,
    default: <Info size={16} weight="fill" />,
  };
  
  const variantMap = {
    created: 'success',
    revoked: 'danger',
    renewed: 'info',
    default: 'default',
  };

  return (
    <div className={styles.activityItem}>
      <div className={styles.activityDot}>
        <GradientBadge variant={variantMap[type] || 'default'} size="sm">
          {iconMap[type] || iconMap.default}
        </GradientBadge>
      </div>
      <div className={styles.activityContent}>
        <div className={styles.activityMessage}>{message}</div>
        <div className={styles.activityMeta}>
          <span>{user}</span>
          <span>•</span>
          <span>{timestamp}</span>
        </div>
      </div>
    </div>
  );
}

export function DashboardV3() {
  const navigate = useNavigate();
  
  const { data: stats, isLoading: statsLoading } = useDashboardStats();
  const { data: overview, isLoading: overviewLoading } = useDashboardOverview();
  const { data: activity, isLoading: activityLoading } = useDashboardActivity(10);
  const { data: expiringCerts, isLoading: expiringLoading } = useDashboardExpiringCerts(5);

  // Mock chart data
  const chartData = [
    { name: 'Jan', value: 12 },
    { name: 'Feb', value: 19 },
    { name: 'Mar', value: 15 },
    { name: 'Apr', value: 25 },
    { name: 'May', value: 22 },
    { name: 'Jun', value: 30 },
    { name: 'Jul', value: 28 },
  ];

  if (statsLoading || overviewLoading) {
    return (
      <div className={styles.dashboard}>
        <Grid cols={4} gap="lg">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} height="120px" />
          ))}
        </Grid>
      </div>
    );
  }

  const statsData = stats || {
    activeCertificates: '247',
    expiringSoon: '12',
    pendingRequests: '3',
    acmeRenewals: '89',
  };

  const overviewData = overview || [
    { label: 'Certificate Authorities', value: '8', icon: 'ShieldCheck' },
    { label: 'Active Users', value: '12', icon: 'Users' },
    { label: 'ACME Accounts', value: '5', icon: 'Globe' },
    { label: 'SCEP Endpoints', value: '2', icon: 'Gear' },
  ];

  const activityData = activity || [
    { type: 'created', message: 'Certificate issued for example.com', user: 'admin', timestamp: '2 minutes ago' },
    { type: 'renewed', message: 'Certificate renewed for api.example.com', user: 'system', timestamp: '1 hour ago' },
    { type: 'revoked', message: 'Certificate revoked for old.example.com', user: 'admin', timestamp: '3 hours ago' },
  ];

  const expiringCertsData = expiringCerts || [];

  return (
    <div className={styles.dashboard}>
      <Stack gap="xl">
        {/* Header */}
        <div>
          <h1 className={styles.title}>Dashboard</h1>
          <p className={styles.subtitle}>Overview of your certificate infrastructure</p>
        </div>

        {/* Stats Cards */}
        <Grid cols={4} gap="lg">
          <StatCardV3
            icon={Certificate}
            value={statsData.activeCertificates}
            label="Active Certificates"
            trend={{ positive: true, text: '+12 this week' }}
            variant="primary"
            onClick={() => navigate('/certificates')}
          />
          <StatCardV3
            icon={Clock}
            value={statsData.expiringSoon}
            label="Expiring Soon"
            sublabel="Within 30 days"
            trend={{ positive: false, text: '5 critical' }}
            variant="warning"
            onClick={() => navigate('/certificates?filter=expiring')}
          />
          <StatCardV3
            icon={FileText}
            value={statsData.pendingRequests}
            label="Pending Requests"
            sublabel="CSRs awaiting approval"
            variant="info"
            onClick={() => navigate('/csrs')}
          />
          <StatCardV3
            icon={Globe}
            value={statsData.acmeRenewals}
            label="ACME Renewals"
            sublabel="Last 30 days"
            trend={{ positive: true, text: '100% success' }}
            variant="success"
            onClick={() => navigate('/acme')}
          />
        </Grid>

        {/* Quick Actions */}
        <div>
          <h2 className={styles.sectionTitle}>Quick Actions</h2>
          <Grid cols={3} gap="lg">
            <QuickActionCard
              icon={Certificate}
              title="Issue Certificate"
              description="Create a new certificate"
              onClick={() => navigate('/certificates/new')}
              gradient="linear-gradient(135deg, var(--color-primary-500) 0%, var(--color-primary-600) 100%)"
            />
            <QuickActionCard
              icon={ShieldCheck}
              title="Create CA"
              description="Set up a new Certificate Authority"
              onClick={() => navigate('/cas/new')}
              gradient="linear-gradient(135deg, var(--color-success-500) 0%, var(--color-success-600) 100%)"
            />
            <QuickActionCard
              icon={FileText}
              title="Import CSR"
              description="Sign a certificate request"
              onClick={() => navigate('/csrs/import')}
              gradient="linear-gradient(135deg, var(--color-info-500) 0%, var(--color-info-600) 100%)"
            />
          </Grid>
        </div>

        {/* Two Column Layout */}
        <Grid cols={2} gap="xl">
          {/* Left: System Overview + Charts */}
          <Stack gap="lg">
            {/* System Overview */}
            <GlassCard blur="md">
              <Stack gap="md">
                <h2 className={styles.sectionTitle}>System Overview</h2>
                <Grid cols={2} gap="md">
                  {overviewData.map((item, idx) => (
                    <div key={idx} className={styles.overviewItem}>
                      <div className={styles.overviewValue}>{item.value}</div>
                      <div className={styles.overviewLabel}>{item.label}</div>
                    </div>
                  ))}
                </Grid>
              </Stack>
            </GlassCard>

            {/* Charts */}
            <GlassCard blur="md">
              <Stack gap="md">
                <div className={styles.chartHeader}>
                  <h2 className={styles.sectionTitle}>Certificates Issued</h2>
                  <GradientBadge variant="blue" size="sm">Last 7 months</GradientBadge>
                </div>
                <div style={{ height: '200px', width: '100%' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="var(--color-primary-500)" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="var(--color-primary-500)" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <Tooltip 
                        contentStyle={{ 
                          background: 'var(--color-bg-secondary)', 
                          border: '1px solid var(--color-border-primary)',
                          borderRadius: '8px'
                        }}
                      />
                      <Area 
                        type="monotone" 
                        dataKey="value" 
                        stroke="var(--color-primary-500)" 
                        strokeWidth={2}
                        fillOpacity={1} 
                        fill="url(#colorValue)" 
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </Stack>
            </GlassCard>

            {/* Alerts */}
            <Stack gap="sm">
              <Alert variant="warning" dismissible>
                <strong>5 certificates</strong> will expire within 7 days
              </Alert>
              <Alert variant="info" dismissible>
                System backup completed successfully
              </Alert>
            </Stack>
          </Stack>

          {/* Right: Activity Feed + Expiring Certs */}
          <Stack gap="lg">
            {/* Recent Activity */}
            <GlassCard blur="md">
              <Stack gap="md">
                <h2 className={styles.sectionTitle}>Recent Activity</h2>
                {activityLoading ? (
                  <Stack gap="sm">
                    {[...Array(3)].map((_, i) => <Skeleton key={i} height="60px" />)}
                  </Stack>
                ) : activityData.length > 0 ? (
                  <div className={styles.activityFeed}>
                    {activityData.map((item, idx) => (
                      <ActivityItem key={idx} {...item} />
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={<Info size={48} />}
                    title="No recent activity"
                    description="Activity will appear here"
                  />
                )}
              </Stack>
            </GlassCard>

            {/* Expiring Certificates */}
            <GlassCard blur="md">
              <Stack gap="md">
                <div className={styles.chartHeader}>
                  <h2 className={styles.sectionTitle}>Expiring Certificates</h2>
                  <Button variant="ghost" size="sm" onClick={() => navigate('/certificates?filter=expiring')}>
                    View All
                  </Button>
                </div>
                {expiringLoading ? (
                  <Stack gap="sm">
                    {[...Array(5)].map((_, i) => <Skeleton key={i} height="40px" />)}
                  </Stack>
                ) : expiringCertsData.length > 0 ? (
                  <Stack gap="xs">
                    {expiringCertsData.slice(0, 5).map((cert, idx) => (
                      <div key={idx} className={styles.certItem}>
                        <div className={styles.certInfo}>
                          <div className={styles.certName}>{cert.name}</div>
                          <div className={styles.certMeta}>{cert.issuer}</div>
                        </div>
                        <GradientBadge 
                          variant={cert.daysLeft <= 7 ? 'orange' : 'blue'}
                          size="sm"
                        >
                          <Clock size={12} weight="bold" />
                          {cert.expiresIn}
                        </GradientBadge>
                      </div>
                    ))}
                  </Stack>
                ) : (
                  <EmptyState
                    icon={<CheckCircle size={48} />}
                    title="All certificates valid"
                    description="No certificates expiring soon"
                  />
                )}
              </Stack>
            </GlassCard>
          </Stack>
        </Grid>
      </Stack>
    </div>
  );
}

export default DashboardV3;
