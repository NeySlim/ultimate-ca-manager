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

const CHART_VARS = {
  primary: '--accent-primary',
  success: '--accent-success',
  warning: '--accent-warning',
  danger: '--accent-danger',
  pro: '--accent-pro',
}

function readChartColors() {
  const style = getComputedStyle(document.documentElement)
  const out = {}
  for (const [key, name] of Object.entries(CHART_VARS)) out[key] = style.getPropertyValue(name).trim()
  return out
}

// Colours are read from the CSS variables at render and re-read when data-theme / data-mode change.
export function useChartColors() {
  const [colors, setColors] = useState(readChartColors)

  useEffect(() => {
    const refresh = () => setColors(readChartColors())
    const observer = new MutationObserver(refresh)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'data-mode'] })
    refresh()
    return () => observer.disconnect()
  }, [])

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
export function CertificateTrendChart({ data = [], height = '100%' }) {
  const { t } = useTranslation()
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
      expired: 0,
    }))
  }, [data])
  
  const strokeColor = colors.primary
  const revokedColor = colors.danger
  const expiredColor = colors.warning
  
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 8, right: 20, left: -20, bottom: 5 }}>
        <defs>
          <linearGradient id="issuedGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={strokeColor} stopOpacity={0.2}/>
            <stop offset="95%" stopColor={strokeColor} stopOpacity={0}/>
          </linearGradient>
        </defs>
        <XAxis 
          dataKey="name" 
          tick={{ fontSize: 12, fill: 'var(--text-tertiary)' }}
          axisLine={false}
          tickLine={false}
          interval={chartData.length <= 7 ? 0 : Math.max(1, Math.floor(chartData.length / 7))}
        />
        <YAxis 
          tick={{ fontSize: 12, fill: 'var(--text-tertiary)' }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
          domain={[0, 'auto']}
        />
        <Tooltip content={<CustomTooltip />} />
        <Area 
          type="basis" 
          dataKey="issued" 
          name={t('common.issued')}
          stroke={strokeColor} 
          fill="url(#issuedGradient)"
          strokeWidth={2}
        />
        <Area 
          type="basis" 
          dataKey="expired" 
          name={t('common.expired')}
          stroke={expiredColor} 
          fill="transparent"
          strokeWidth={2}
        />
        <Area 
          type="basis" 
          dataKey="revoked" 
          name={t('common.revoked')}
          stroke={revokedColor} 
          fill="transparent"
          strokeWidth={2}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// Status distribution pie chart
export function StatusPieChart({ data = {}, height = '100%', onSegmentClick }) {
  const { t } = useTranslation()
  const colors = useChartColors()
  
  const chartData = useMemo(() => {
    const { valid = 0, expiring = 0, expired = 0, revoked = 0 } = data
    return [
      { name: t('common.valid'), value: valid, color: colors.success, statusKey: 'valid' },
      { name: t('common.expiring'), value: expiring, color: colors.warning, statusKey: 'expiring' },
      { name: t('common.expired'), value: expired, color: colors.danger, statusKey: 'expired' },
      { name: t('common.revoked'), value: revoked, color: colors.pro, statusKey: 'revoked' },
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
        <defs>
          <filter id="donutShadow" x="-10%" y="-10%" width="120%" height="120%">
            <feDropShadow dx="0" dy="1" stdDeviation="2" floodOpacity="0.15" />
          </filter>
          {chartData.map((entry, i) => (
            <linearGradient key={`grad-${i}`} id={`donut-grad-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={entry.color} stopOpacity={1} />
              <stop offset="100%" stopColor={entry.color} stopOpacity={0.7} />
            </linearGradient>
          ))}
        </defs>
        <Pie
          data={chartData}
          cx="35%"
          cy="50%"
          innerRadius="40%"
          outerRadius="70%"
          paddingAngle={3}
          dataKey="value"
          stroke="color-mix(in srgb, var(--text) 15%, transparent)"
          strokeWidth={1}
          style={{ filter: 'url(#donutShadow)' }}
          cornerRadius={3}
        >
          {chartData.map((entry, i) => (
            <Cell 
              key={i} 
              fill={`url(#donut-grad-${i})`} 
              style={onSegmentClick ? { cursor: 'pointer' } : undefined}
              onClick={onSegmentClick ? () => onSegmentClick(entry.statusKey) : undefined}
            />
          ))}
        </Pie>
        <Tooltip content={<CustomTooltip />} />
        <Legend 
          verticalAlign="middle" 
          align="right"
          layout="vertical"
          iconSize={8}
          iconType="circle"
          wrapperStyle={{ fontSize: 12, paddingLeft: 4 }}
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
          type="basis" 
          dataKey="value" 
          stroke={strokeColor} 
          fill={`url(#spark-${color})`}
          strokeWidth={1.5}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
