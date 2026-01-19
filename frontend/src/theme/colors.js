// UCM Color Palettes - Based on design-system.html
// 6 color themes with subtle gradients (135deg linear)

export const colorPalettes = {
  'blue-sky': {
    name: 'Blue Sky',
    gradient: {
      start: '#5a8fc7',
      end: '#7aa5d9'
    },
    colors: {
      light: '#7aa5d9',
      main: '#5a8fc7',
      dark: '#4a7fb7'
    }
  },
  'purple-dream': {
    name: 'Purple Dream',
    gradient: {
      start: '#9985c7',
      end: '#b5a3d9'
    },
    colors: {
      light: '#b5a3d9',
      main: '#9985c7',
      dark: '#8975b7'
    }
  },
  'mint-fresh': {
    name: 'Mint Fresh',
    gradient: {
      start: '#5eb89b',
      end: '#7bc9af'
    },
    colors: {
      light: '#7bc9af',
      main: '#5eb89b',
      dark: '#4ea88b'
    }
  },
  'amber-warm': {
    name: 'Amber Warm',
    gradient: {
      start: '#c99652',
      end: '#d9ac73'
    },
    colors: {
      light: '#d9ac73',
      main: '#c99652',
      dark: '#b98642'
    }
  },
  'mokka': {
    name: 'Mokka',
    gradient: {
      start: '#b8926d',
      end: '#c9a687'
    },
    colors: {
      light: '#c9a687',
      main: '#b8926d',
      dark: '#a8825d'
    }
  },
  'pink-soft': {
    name: 'Pink Soft',
    gradient: {
      start: '#c77799',
      end: '#d994ad'
    },
    colors: {
      light: '#d994ad',
      main: '#c77799',
      dark: '#b76789'
    }
  }
};

export const baseColors = {
  // Dark theme backgrounds
  dark: {
    bg: {
      primary: '#1a1a1a',
      secondary: '#1e1e1e',
      tertiary: '#252525',
      card: '#2a2a2a',
      hover: '#333333'
    },
    text: {
      primary: '#e8e8e8',
      secondary: '#cccccc',
      tertiary: '#888888'
    },
    border: '#3a3a3a',
    shadow: 'rgba(0, 0, 0, 0.5)'
  },
  
  // Status colors
  status: {
    success: '#81c784',
    warning: '#ffb74d',
    error: '#e57373',
    info: '#64b5f6'
  }
};

export default { colorPalettes, baseColors };
