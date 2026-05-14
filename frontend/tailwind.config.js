/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // ── Primary cold blue palette ──────────────────────────────────────
        primary: {
          DEFAULT: '#3B82F6',   // blue-500
          dark:    '#2563EB',   // blue-600
          light:   '#60A5FA',   // blue-400
          subtle:  '#EFF6FF',   // blue-50
          muted:   '#DBEAFE',   // blue-100
        },
        // ── Secondary slate ────────────────────────────────────────────────
        secondary: {
          DEFAULT: '#64748B',   // slate-500
          light:   '#94A3B8',   // slate-400
          dark:    '#475569',   // slate-600
        },
        // ── Backgrounds ────────────────────────────────────────────────────
        base:    '#F8FAFC',    // slate-50  — page bg
        surface: '#FFFFFF',    // pure white — cards
        // ── Semantic ───────────────────────────────────────────────────────
        success: '#10B981',    // emerald-500
        danger:  '#EF4444',    // red-500
        warning: '#F59E0B',    // amber-500
        // ── Borders ────────────────────────────────────────────────────────
        border: {
          DEFAULT: '#E2E8F0',  // slate-200
          strong:  '#CBD5E1',  // slate-300
        },
        // ── Text ───────────────────────────────────────────────────────────
        ink: {
          DEFAULT: '#0F172A',  // slate-900
          secondary: '#334155', // slate-700
          muted:     '#64748B', // slate-500
          faint:     '#94A3B8', // slate-400
        },
        // ── Teal accent (second accent) ────────────────────────────────────
        teal: {
          DEFAULT: '#14B8A6',
          light:   '#CCFBF1',
          subtle:  '#F0FDFA',
        },
      },

      fontFamily: {
        sans:    ['Inter', 'Satoshi', 'system-ui', 'sans-serif'],
        heading: ['Inter', 'Satoshi', 'sans-serif'],
        mono:    ['JetBrains Mono', 'Fira Code', 'monospace'],
      },

      borderRadius: {
        card: '14px',
        btn:  '10px',
        pill: '999px',
      },

      boxShadow: {
        card:       '0 1px 3px rgba(15,23,42,0.06), 0 4px 16px rgba(15,23,42,0.06)',
        'card-md':  '0 2px 8px rgba(15,23,42,0.08), 0 8px 24px rgba(15,23,42,0.08)',
        'card-hover': '0 4px 12px rgba(59,130,246,0.12), 0 12px 32px rgba(59,130,246,0.10)',
        'input-focus': '0 0 0 3px rgba(59,130,246,0.15)',
        'btn-primary': '0 2px 8px rgba(37,99,235,0.25)',
      },

      animation: {
        shimmer:    'shimmer 2s infinite linear',
        fade_in:    'fadeIn 0.35s ease-out',
        slide_up:   'slideUp 0.35s ease-out',
      },

      keyframes: {
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        fadeIn: {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        slideUp: {
          from: { opacity: '0', transform: 'translateY(12px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
};
