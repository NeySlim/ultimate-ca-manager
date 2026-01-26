/**
 * 📝 TYPOGRAPHY FOUNDATION
 * Font stacks, scales, weights, line heights
 */

export const typography = {
  // Font families
  fonts: {
    sans: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    mono: '"JetBrains Mono", "Fira Code", Consolas, Monaco, monospace',
  },
  
  // Font sizes (px → rem)
  sizes: {
    'xs': '0.75rem',    // 12px
    'sm': '0.875rem',   // 14px
    'base': '1rem',     // 16px
    'lg': '1.125rem',   // 18px
    'xl': '1.25rem',    // 20px
    '2xl': '1.5rem',    // 24px
    '3xl': '1.875rem',  // 30px
    '4xl': '2.25rem',   // 36px
    '5xl': '3rem',      // 48px
    '6xl': '3.75rem',   // 60px
    '7xl': '4.5rem',    // 72px
    '8xl': '6rem',      // 96px
  },
  
  // Font weights
  weights: {
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
  
  // Line heights
  leading: {
    none: 1,
    tight: 1.25,
    snug: 1.375,
    normal: 1.5,
    relaxed: 1.625,
    loose: 2,
  },
  
  // Letter spacing
  tracking: {
    tighter: '-0.05em',
    tight: '-0.025em',
    normal: '0',
    wide: '0.025em',
    wider: '0.05em',
    widest: '0.1em',
  },
};

export function getTypographyVariables() {
  return {
    '--font-sans': typography.fonts.sans,
    '--font-mono': typography.fonts.mono,
    
    '--text-xs': typography.sizes.xs,
    '--text-sm': typography.sizes.sm,
    '--text-base': typography.sizes.base,
    '--text-lg': typography.sizes.lg,
    '--text-xl': typography.sizes.xl,
    '--text-2xl': typography.sizes['2xl'],
    '--text-3xl': typography.sizes['3xl'],
    '--text-4xl': typography.sizes['4xl'],
    '--text-5xl': typography.sizes['5xl'],
    '--text-6xl': typography.sizes['6xl'],
    '--text-7xl': typography.sizes['7xl'],
    '--text-8xl': typography.sizes['8xl'],
    
    '--font-normal': typography.weights.normal,
    '--font-medium': typography.weights.medium,
    '--font-semibold': typography.weights.semibold,
    '--font-bold': typography.weights.bold,
    
    '--leading-none': typography.leading.none,
    '--leading-tight': typography.leading.tight,
    '--leading-snug': typography.leading.snug,
    '--leading-normal': typography.leading.normal,
    '--leading-relaxed': typography.leading.relaxed,
    '--leading-loose': typography.leading.loose,
    
    '--tracking-tighter': typography.tracking.tighter,
    '--tracking-tight': typography.tracking.tight,
    '--tracking-normal': typography.tracking.normal,
    '--tracking-wide': typography.tracking.wide,
    '--tracking-wider': typography.tracking.wider,
    '--tracking-widest': typography.tracking.widest,
  };
}
