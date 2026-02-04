/**
 * DashboardChart - Interactive chart component for dashboard
 * Uses Recharts for beautiful responsive charts
 */
import { useMemo } from 'react'
import { 
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend
} from 'recharts'
import { useTheme } from '../contexts/ThemeContext'

// Custom tooltip component
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  
  return (
    <div className="bg-bg-secondary border border-border rounded-lg px-3 py-2 shadow-lg">
      <p className="text-xs text-text-secondary mb-1">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="text-sm font-medium" style={{ color: entry.color }}>
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  )
}

// Certificate trend chart (area chart)
export function CertificateTrendChart({ data = [], height = 150 }) {
  const { mode } = useTheme()
  
  // Generate sample data if none provided
  const chartData = useMemo(() => {
    if (data.length > 0) return data
    
    // Generate last 7 days of fake data for demo
    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    return days.map((day, i) => ({
      name: day,
      issued: Math.floor(Math.random() * 5) + 1,
      revoked: Math.floor(Math.random() * 2),
    }))
  }, [data])
  
  const strokeColor = mode === 'dark' ? '#60a5fa' : '#3b82f6'
  const fillColor = mode === 'dark' ? 'rgba(96, 165, 250, 0.15)' : 'rgba(59, 130, 246, 0.2)'
  const revokedColor = mode === 'dark' ? '#f87171' : '#ef4444'
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
          name="Issued"
          stroke={strokeColor} 
          fill="url(#issuedGradient)"
          strokeWidth={2}
        />
        <Area 
          type="monotone" 
          dataKey="revoked" 
          name="Revoked"
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
export function StatusPieChart({ data = {}, height = 150 }) {
  const { mode } = useTheme()
  
  const chartData = useMemo(() => {
    const { valid = 0, expiring = 0, expired = 0, revoked = 0 } = data
    return [
      { name: 'Valid', value: valid, color: mode === 'dark' ? '#4ade80' : '#22c55e' },
      { name: 'Expiring', value: expiring, color: mode === 'dark' ? '#fbbf24' : '#f59e0b' },
      { name: 'Expired', value: expired, color: mode === 'dark' ? '#f87171' : '#ef4444' },
      { name: 'Revoked', value: revoked, color: mode === 'dark' ? '#a78bfa' : '#8b5cf6' },
    ].filter(d => d.value > 0)
  }, [data, mode])
  
  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-text-tertiary text-sm">
        No data available
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
          innerRadius={35}
          outerRadius={55}
          paddingAngle={2}
          dataKey="value"
          strokeWidth={0}
        >
          {chartData.map((entry, index) => (
            <Cell key={index} fill={entry.color} />
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
  const { mode } = useTheme()
  
  const strokeColor = {
    blue: mode === 'dark' ? '#60a5fa' : '#3b82f6',
    green: mode === 'dark' ? '#4ade80' : '#22c55e',
    red: mode === 'dark' ? '#f87171' : '#ef4444',
    yellow: mode === 'dark' ? '#fbbf24' : '#f59e0b',
  }[color] || '#60a5fa'
  
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
