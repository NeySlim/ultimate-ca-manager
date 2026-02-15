/**
 * DashboardChart - Interactive chart component for dashboard
 * Uses Recharts for beautiful responsive charts
 */
import { useMemo, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend
} from 'recharts'
import { useTheme } from '../contexts/ThemeContext'

// Get computed CSS variable value
function getCssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

// Hook to get chart colors from CSS variables
function useChartColors() {
  const { mode } = useTheme()
  const [colors, setColors] = useState({
    primary: '#3b82f6',
    success: '#22c55e',
    warning: '#f59e0b',
    danger: '#ef4444',
    pro: '#8b5cf6',
  })
  
  useEffect(() => {
    // Read colors from CSS variables after theme change
    const timer = setTimeout(() => {
      setColors({
        primary: getCssVar('--accent-primary') || '#3b82f6',
        success: getCssVar('--accent-success') || '#22c55e',
        warning: getCssVar('--accent-warning') || '#f59e0b',
        danger: getCssVar('--accent-danger') || '#ef4444',
        pro: getCssVar('--accent-pro') || '#8b5cf6',
      })
    }, 50) // Small delay to ensure CSS is applied
    return () => clearTimeout(timer)
  }, [mode])
  
  return colors
}

// Custom tooltip component
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  
  return (
    <div className="bg-bg-secondary border border-border rounded-lg px-3 py-2 shadow-lg">
      <p className="text-xs text-text-secondary mb-1">{label}</p>
      {payload.map((entry, i) => (
        <p key={entry.name || i} className="text-sm font-medium" style={{ color: entry.color }}>
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  )
}

// Certificate trend chart (area chart)
export function CertificateTrendChart({ data = [], height = 250 }) {
  const { t } = useTranslation()
  const { mode } = useTheme()
  const colors = useChartColors()
  
  // Use provided data directly
  const chartData = useMemo(() => {
    if (data.length > 0) return data
    
    // Return empty placeholder data if no data provided
    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    return days.map(day => ({
      name: day,
      issued: 0,
      revoked: 0,
    }))
  }, [data])
  
  const strokeColor = colors.primary
  const fillColor = `${colors.primary}30`
  const revokedColor = colors.danger
  const gridColor = mode === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)'
  
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="issuedGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={strokeColor} stopOpacity={0.2}/>
            <stop offset="95%" stopColor={strokeColor} stopOpacity={0}/>
          </linearGradient>
        </defs>
        <XAxis 
          dataKey="name" 
          tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis 
          tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
        />
        <Tooltip content={<CustomTooltip />} />
        <Area 
          type="monotone" 
          dataKey="issued" 
          name={t('common.issued')}
          stroke={strokeColor} 
          fill="url(#issuedGradient)"
          strokeWidth={2}
        />
        <Area 
          type="monotone" 
          dataKey="revoked" 
          name={t('common.revoked')}
          stroke={revokedColor} 
          fill="transparent"
          strokeWidth={2}
          strokeDasharray="3 3"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// Status distribution pie chart
export function StatusPieChart({ data = {}, height = 250 }) {
  const { t } = useTranslation()
  const colors = useChartColors()
  
  const chartData = useMemo(() => {
    const { valid = 0, expiring = 0, expired = 0, revoked = 0 } = data
    return [
      { name: t('common.valid'), value: valid, color: colors.success },
      { name: t('common.expiring'), value: expiring, color: colors.warning },
      { name: t('common.expired'), value: expired, color: colors.danger },
      { name: t('common.revoked'), value: revoked, color: colors.pro },
    ].filter(d => d.value > 0)
  }, [data, colors, t])
  
  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-text-tertiary text-sm">
        {t('common.noDataAvailable')}
      </div>
    )
  }
  
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius="30%"
          outerRadius="50%"
          paddingAngle={2}
          dataKey="value"
          strokeWidth={0}
        >
          {chartData.map((entry, index) => (
            <Cell key={entry.name} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip content={<CustomTooltip />} />
        <Legend 
          verticalAlign="middle" 
          align="right"
          layout="vertical"
          iconSize={8}
          iconType="circle"
          wrapperStyle={{ fontSize: 11, paddingLeft: 10 }}
          formatter={(value) => <span className="text-text-secondary">{value}</span>}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}

// Simple mini sparkline
export function MiniSparkline({ data = [], color = 'blue', height = 30 }) {
  const colors = useChartColors()
  
  const colorMap = {
    blue: colors.primary,
    green: colors.success,
    red: colors.danger,
    yellow: colors.warning,
  }
  const strokeColor = colorMap[color] || colors.primary
  
  if (data.length === 0) return null
  
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={`spark-${color}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={strokeColor} stopOpacity={0.3}/>
            <stop offset="95%" stopColor={strokeColor} stopOpacity={0}/>
          </linearGradient>
        </defs>
        <Area 
          type="monotone" 
          dataKey="value" 
          stroke={strokeColor} 
          fill={`url(#spark-${color})`}
          strokeWidth={1.5}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
