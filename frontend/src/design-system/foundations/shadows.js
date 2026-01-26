/**
 * 🌑 SHADOWS FOUNDATION
 * Multi-layer elevation system
 */

export const shadows = {
  dark: {
    sm: '0 1px 2px 0 rgba(0, 0, 0, 0.5)',
    md: '0 4px 6px -1px rgba(0, 0, 0, 0.5), 0 2px 4px -1px rgba(0, 0, 0, 0.3)',
    lg: '0 10px 15px -3px rgba(0, 0, 0, 0.5), 0 4px 6px -2px rgba(0, 0, 0, 0.3)',
    xl: '0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.2)',
    '2xl': '0 25px 50px -12px rgba(0, 0, 0, 0.6)',
    none: 'none',
    
    // Glow effects
    'glow-blue': '0 0 20px rgba(0, 168, 252, 0.4)',
    'glow-mint': '0 0 20px rgba(35, 160, 148, 0.4)',
    'glow-purple': '0 0 20px rgba(156, 39, 176, 0.4)',
  },
  
  light: {
    sm: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
    md: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
    lg: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
    xl: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
    '2xl': '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
    none: 'none',
    
    // Glow effects
    'glow-blue': '0 0 20px rgba(33, 150, 243, 0.3)',
    'glow-mint': '0 0 20px rgba(0, 191, 165, 0.3)',
    'glow-purple': '0 0 20px rgba(156, 39, 176, 0.3)',
  },
};

export function getShadowVariables(theme = 'dark') {
  const vars = {};
  Object.entries(shadows[theme]).forEach(([key, value]) => {
    vars[`--shadow-${key}`] = value;
  });
  return vars;
}
