/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        cyber: {
          black: '#0a0a0f',
          dark: '#0d0d14',
          card: '#12121a',
          border: '#1a1a2e',
          cyan: '#00d4ff',
          'cyan-dim': '#00a8cc',
          violet: '#7c3aed',
          'violet-dim': '#5b21b6',
          emerald: '#10b981',
          'emerald-dim': '#059669',
          amber: '#f59e0b',
          pink: '#ec4899',
          gray: '#6b7280',
        },
      },
      fontFamily: {
        heading: ['Cabinet Grotesk', 'Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        body: ['Satoshi', 'Inter', 'sans-serif'],
      },
      animation: {
        shimmer: 'shimmer 2s infinite linear',
        pulse_slow: 'pulse 3s ease-in-out infinite',
        float: 'float 6s ease-in-out infinite',
        glow: 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        glow: {
          from: { boxShadow: '0 0 10px rgba(0,212,255,0.2)' },
          to: { boxShadow: '0 0 30px rgba(0,212,255,0.6)' },
        },
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
};
