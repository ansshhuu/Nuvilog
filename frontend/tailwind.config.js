/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: 'var(--color-background)',
        surface: 'var(--color-surface)',
        border: 'var(--color-border)',
        'text-primary': 'var(--color-text-primary)',
        'text-muted': 'var(--color-text-muted)',
        accent: 'var(--color-accent)',
        selected: 'var(--color-selected)',
        'status-verbatim': 'var(--color-status-verbatim)',
        'status-inferred': 'var(--color-status-inferred)',
        'status-unverified': 'var(--color-status-unverified)',
        'status-contradiction': 'var(--color-status-contradiction)',
        'not-built': 'var(--color-not-built)',
      },
      /**
       * Density scale. The mockup is a dense instrument panel, not a
       * marketing page: body text reads ~13px and table/label text ~10-11px.
       * Named tokens instead of arbitrary text-[Npx] values so the whole app
       * can be re-scaled from one place.
       */
      fontSize: {
        '3xs': ['9px', { lineHeight: '12px' }],
        '2xs': ['10px', { lineHeight: '14px' }],
        xs: ['11px', { lineHeight: '15px' }],
        sm: ['12px', { lineHeight: '16px' }],
        base: ['13px', { lineHeight: '18px' }],
        lg: ['15px', { lineHeight: '20px' }],
        xl: ['19px', { lineHeight: '24px' }],
      },

      /**
       * Tailwind's spacing scale compressed to 0.8x (1 unit = 0.2rem rather
       * than 0.25rem). This is the global density lever: every p-, m-, gap-,
       * w-N and h-N in the app tightens proportionally, so padding and row
       * heights stay in the same relationship to each other instead of being
       * nudged component by component. Change the 0.8 below to re-scale.
       */
      spacing: Object.fromEntries(
        [
          0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16,
          20, 24, 28, 32,
        ].map((step) => [step, `${step * 0.25 * 0.8}rem`]),
      ),

      fontFamily: {
        mono: ['JetBrains Mono', 'IBM Plex Mono', 'ui-monospace', 'monospace'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      // Hard cap: nothing in this app is rounder than 4px.
      borderRadius: {
        none: '0px',
        sm: '2px',
        DEFAULT: '3px',
        md: '4px',
        lg: '4px',
        xl: '4px',
        '2xl': '4px',
        '3xl': '4px',
        // `full` stays circular — it is only for dots/pills, never box corners.
        full: '9999px',
      },
    },
  },
  plugins: [],
}
