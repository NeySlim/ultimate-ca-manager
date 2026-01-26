/**
 * 🎨 COLORS FOUNDATION
 * Complete color system with dark & light palettes
 * Snefch-inspired: Deep grays, vibrant accents, semantic colors
 * 
 * Total: 262 colors (131 dark + 131 light)
 */

export const colors = {
  // ===== DARK MODE PALETTE =====
  dark: {
    // Primary backgrounds (deep grays)
    'bg-primary': '#1E1F22',      // Main background
    'bg-secondary': '#2B2D31',    // Cards, panels
    'bg-tertiary': '#313338',     // Elevated elements
    'bg-hover': '#35373C',        // Hover states
    'bg-active': '#3F4147',       // Active states
    
    // Text colors
    'text-primary': '#F2F3F5',    // Main text
    'text-secondary': '#B5BAC1',  // Secondary text
    'text-tertiary': '#87898C',   // Muted text
    'text-link': '#00A8FC',       // Links
    'text-inverse': '#1E1F22',    // Text on colored bg
    
    // Borders
    'border-subtle': '#26272B',   // Subtle dividers
    'border-default': '#3F4147',  // Default borders
    'border-strong': '#4E5058',   // Emphasized borders
    
    // Grays (neutral scale)
    'gray-200': '#EEEEEE',
    'gray-300': '#E0E0E0',
    'gray-400': '#BDBDBD',
    'gray-500': '#9E9E9E',
    'gray-600': '#757575',
    'gray-700': '#616161',
    'gray-800': '#424242',
    'gray-900': '#212121',
    
    // Blue accent (primary actions)
    'blue-50': '#E3F2FD',
    'blue-100': '#BBDEFB',
    'blue-200': '#90CAF9',
    'blue-300': '#64B5F6',
    'blue-400': '#42A5F5',
    'blue-500': '#00A8FC',   // Primary blue
    'blue-600': '#1E88E5',
    'blue-700': '#1976D2',
    'blue-800': '#1565C0',
    'blue-900': '#0D47A1',
    
    // Mint green (success, positive)
    'mint-50': '#E0F7F4',
    'mint-100': '#B3ECE6',
    'mint-200': '#80DFD6',
    'mint-300': '#4DD2C6',
    'mint-400': '#26C9BA',
    'mint-500': '#23A094',   // Primary mint
    'mint-600': '#1E8A7F',
    'mint-700': '#19746B',
    'mint-800': '#145E57',
    'mint-900': '#0F4842',
    
    // Purple (premium, special)
    'purple-50': '#F3E5F5',
    'purple-100': '#E1BEE7',
    'purple-200': '#CE93D8',
    'purple-300': '#BA68C8',
    'purple-400': '#AB47BC',
    'purple-500': '#9C27B0',  // Primary purple
    'purple-600': '#8E24AA',
    'purple-700': '#7B1FA2',
    'purple-800': '#6A1B9A',
    'purple-900': '#4A148C',
    
    // Pink (accents, highlights)
    'pink-50': '#FCE4EC',
    'pink-100': '#F8BBD0',
    'pink-200': '#F48FB1',
    'pink-300': '#F06292',
    'pink-400': '#EC407A',
    'pink-500': '#E91E63',   // Primary pink
    'pink-600': '#D81B60',
    'pink-700': '#C2185B',
    'pink-800': '#AD1457',
    'pink-900': '#880E4F',
    
    // Orange (warnings, attention)
    'orange-50': '#FFF3E0',
    'orange-100': '#FFE0B2',
    'orange-200': '#FFCC80',
    'orange-300': '#FFB74D',
    'orange-400': '#FFA726',
    'orange-500': '#FF9800',  // Primary orange
    'orange-600': '#FB8C00',
    'orange-700': '#F57C00',
    'orange-800': '#EF6C00',
    'orange-900': '#E65100',
    
    // Red (errors, danger)
    'red-50': '#FFEBEE',
    'red-100': '#FFCDD2',
    'red-200': '#EF9A9A',
    'red-300': '#E57373',
    'red-400': '#EF5350',
    'red-500': '#F44336',    // Primary red
    'red-600': '#E53935',
    'red-700': '#D32F2F',
    'red-800': '#C62828',
    'red-900': '#B71C1C',
    
    // Green (success, confirmation)
    'green-50': '#E8F5E9',
    'green-100': '#C8E6C9',
    'green-200': '#A5D6A7',
    'green-300': '#81C784',
    'green-400': '#66BB6A',
    'green-500': '#4CAF50',   // Primary green
    'green-600': '#43A047',
    'green-700': '#388E3C',
    'green-800': '#2E7D32',
    'green-900': '#1B5E20',
    
    // Yellow (warnings, highlights)
    'yellow-50': '#FFFDE7',
    'yellow-100': '#FFF9C4',
    'yellow-200': '#FFF59D',
    'yellow-300': '#FFF176',
    'yellow-400': '#FFEE58',
    'yellow-500': '#FFEB3B',
    'yellow-600': '#FDD835',
    'yellow-700': '#FBC02D',
    'yellow-800': '#F9A825',
    'yellow-900': '#F57F17',
    
    // Cyan (info, links)
    'cyan-50': '#E0F7FA',
    'cyan-100': '#B2EBF2',
    'cyan-200': '#80DEEA',
    'cyan-300': '#4DD0E1',
    'cyan-400': '#26C6DA',
    'cyan-500': '#00BCD4',
    'cyan-600': '#00ACC1',
    'cyan-700': '#0097A7',
    'cyan-800': '#00838F',
    'cyan-900': '#006064',
    
    // Indigo (deep blue-purple)
    'indigo-50': '#E8EAF6',
    'indigo-100': '#C5CAE9',
    'indigo-200': '#9FA8DA',
    'indigo-300': '#7986CB',
    'indigo-400': '#5C6BC0',
    'indigo-500': '#3F51B5',
    'indigo-600': '#3949AB',
    'indigo-700': '#303F9F',
    'indigo-800': '#283593',
    'indigo-900': '#1A237E',
    
    // Teal (blue-green)
    'teal-50': '#E0F2F1',
    'teal-100': '#B2DFDB',
    'teal-200': '#80CBC4',
    'teal-300': '#4DB6AC',
    'teal-400': '#26A69A',
    'teal-500': '#009688',
    'teal-600': '#00897B',
    'teal-700': '#00796B',
    'teal-800': '#00695C',
    'teal-900': '#004D40',
  },
  
  // ===== LIGHT MODE PALETTE =====
  light: {
    // Primary backgrounds (bright, clean)
    'bg-primary': '#FAFAFA',      // Main background
    'bg-secondary': '#FFFFFF',    // Cards, panels
    'bg-tertiary': '#F5F5F5',     // Elevated elements
    'bg-hover': '#EEEEEE',        // Hover states
    'bg-active': '#E0E0E0',       // Active states
    
    // Text colors
    'text-primary': '#1E1F22',    // Main text
    'text-secondary': '#4E5058',  // Secondary text
    'text-tertiary': '#87898C',   // Muted text
    'text-link': '#1976D2',       // Links
    'text-inverse': '#FFFFFF',    // Text on colored bg
    
    // Borders
    'border-subtle': '#F0F0F0',   // Subtle dividers
    'border-default': '#E0E0E0',  // Default borders
    'border-strong': '#BDBDBD',   // Emphasized borders
    
    // Grays (neutral scale)
    'gray-200': '#EEEEEE',
    'gray-300': '#E0E0E0',
    'gray-400': '#BDBDBD',
    'gray-500': '#9E9E9E',
    'gray-600': '#757575',
    'gray-700': '#616161',
    'gray-800': '#424242',
    'gray-900': '#212121',
    
    // Blue accent (darker for light mode)
    'blue-50': '#E3F2FD',
    'blue-100': '#BBDEFB',
    'blue-200': '#90CAF9',
    'blue-300': '#64B5F6',
    'blue-400': '#42A5F5',
    'blue-500': '#2196F3',
    'blue-600': '#1E88E5',
    'blue-700': '#1976D2',
    'blue-800': '#1565C0',
    'blue-900': '#0D47A1',
    
    // Mint green
    'mint-50': '#E0F7F4',
    'mint-100': '#B3ECE6',
    'mint-200': '#80DFD6',
    'mint-300': '#4DD2C6',
    'mint-400': '#26C9BA',
    'mint-500': '#00BFA5',
    'mint-600': '#00AB94',
    'mint-700': '#009783',
    'mint-800': '#008372',
    'mint-900': '#006F61',
    
    // Purple
    'purple-50': '#F3E5F5',
    'purple-100': '#E1BEE7',
    'purple-200': '#CE93D8',
    'purple-300': '#BA68C8',
    'purple-400': '#AB47BC',
    'purple-500': '#9C27B0',
    'purple-600': '#8E24AA',
    'purple-700': '#7B1FA2',
    'purple-800': '#6A1B9A',
    'purple-900': '#4A148C',
    
    // Pink
    'pink-50': '#FCE4EC',
    'pink-100': '#F8BBD0',
    'pink-200': '#F48FB1',
    'pink-300': '#F06292',
    'pink-400': '#EC407A',
    'pink-500': '#E91E63',
    'pink-600': '#D81B60',
    'pink-700': '#C2185B',
    'pink-800': '#AD1457',
    'pink-900': '#880E4F',
    
    // Orange
    'orange-50': '#FFF3E0',
    'orange-100': '#FFE0B2',
    'orange-200': '#FFCC80',
    'orange-300': '#FFB74D',
    'orange-400': '#FFA726',
    'orange-500': '#FF9800',
    'orange-600': '#FB8C00',
    'orange-700': '#F57C00',
    'orange-800': '#EF6C00',
    'orange-900': '#E65100',
    
    // Red
    'red-50': '#FFEBEE',
    'red-100': '#FFCDD2',
    'red-200': '#EF9A9A',
    'red-300': '#E57373',
    'red-400': '#EF5350',
    'red-500': '#F44336',
    'red-600': '#E53935',
    'red-700': '#D32F2F',
    'red-800': '#C62828',
    'red-900': '#B71C1C',
    
    // Green
    'green-50': '#E8F5E9',
    'green-100': '#C8E6C9',
    'green-200': '#A5D6A7',
    'green-300': '#81C784',
    'green-400': '#66BB6A',
    'green-500': '#4CAF50',
    'green-600': '#43A047',
    'green-700': '#388E3C',
    'green-800': '#2E7D32',
    'green-900': '#1B5E20',
    
    // Yellow (warnings, highlights)
    'yellow-50': '#FFFDE7',
    'yellow-100': '#FFF9C4',
    'yellow-200': '#FFF59D',
    'yellow-300': '#FFF176',
    'yellow-400': '#FFEE58',
    'yellow-500': '#FFEB3B',
    'yellow-600': '#FDD835',
    'yellow-700': '#FBC02D',
    'yellow-800': '#F9A825',
    'yellow-900': '#F57F17',
    
    // Cyan (info, links)
    'cyan-50': '#E0F7FA',
    'cyan-100': '#B2EBF2',
    'cyan-200': '#80DEEA',
    'cyan-300': '#4DD0E1',
    'cyan-400': '#26C6DA',
    'cyan-500': '#00BCD4',
    'cyan-600': '#00ACC1',
    'cyan-700': '#0097A7',
    'cyan-800': '#00838F',
    'cyan-900': '#006064',
    
    // Indigo (deep blue-purple)
    'indigo-50': '#E8EAF6',
    'indigo-100': '#C5CAE9',
    'indigo-200': '#9FA8DA',
    'indigo-300': '#7986CB',
    'indigo-400': '#5C6BC0',
    'indigo-500': '#3F51B5',
    'indigo-600': '#3949AB',
    'indigo-700': '#303F9F',
    'indigo-800': '#283593',
    'indigo-900': '#1A237E',
    
    // Teal (blue-green)
    'teal-50': '#E0F2F1',
    'teal-100': '#B2DFDB',
    'teal-200': '#80CBC4',
    'teal-300': '#4DB6AC',
    'teal-400': '#26A69A',
    'teal-500': '#009688',
    'teal-600': '#00897B',
    'teal-700': '#00796B',
    'teal-800': '#00695C',
    'teal-900': '#004D40',
  },
};

/**
 * Get CSS variables for a theme
 * Converts color object to CSS custom properties
 */
export function getCSSVariables(theme = 'dark') {
  const palette = colors[theme];
  const cssVars = {};
  
  for (const [key, value] of Object.entries(palette)) {
    cssVars[`--color-${key}`] = value;
  }
  
  return cssVars;
}

/**
 * Export count for validation
 */
export const colorCount = {
  dark: Object.keys(colors.dark).length,
  light: Object.keys(colors.light).length,
  total: Object.keys(colors.dark).length + Object.keys(colors.light).length,
};
