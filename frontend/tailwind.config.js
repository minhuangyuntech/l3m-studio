/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: {
          DEFAULT: 'var(--bg-paper)',
          card: 'var(--bg-card)',
          subtle: 'var(--bg-subtle)',
          border: 'var(--border-paper)',
        },
        terracotta: {
          DEFAULT: 'var(--accent-primary)',
          dark: 'var(--accent-primary-hover)',
          soft: 'var(--accent-soft)',
        },
        aurora: {
          cyan: '#06b6d4',
          indigo: '#6366f1',
          violet: '#8b5cf6',
        },
        slateink: {
          DEFAULT: 'var(--text-ink)',
          muted: 'var(--text-muted)',
          navy: '#0f172a',
          panel: '#162033',
        },
      },
      fontFamily: {
        sans: ['"Noto Sans TC"', '"Inter"', '"PingFang TC"', '"Microsoft JhengHei"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Cascadia Code"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
};
