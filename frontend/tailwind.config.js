/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        background: '#0B0F12',
        surface: '#11161B',
        'surface-hover': '#161D24',
        border: '#1C242D',
        'border-focus': '#2E3A48',
        accent: {
          DEFAULT: '#97CEB4',
          dim: 'rgba(151, 206, 180, 0.15)',
          glow: 'rgba(151, 206, 180, 0.35)',
        },
        danger: {
          DEFAULT: '#FF0055',
          dim: 'rgba(255, 0, 85, 0.15)',
          glow: 'rgba(255, 0, 85, 0.35)',
        },
        warning: {
          DEFAULT: '#F5A623',
          dim: 'rgba(245, 166, 35, 0.15)',
        },
        muted: '#5A6878',
        text: '#DCE4EC',
        'text-dim': '#8B9AA8',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: {
        'glow-accent': '0 0 20px -3px rgba(151, 206, 180, 0.25)',
        'glow-danger': '0 0 20px -3px rgba(255, 0, 85, 0.3)',
      }
    },
  },
  plugins: [],
};
