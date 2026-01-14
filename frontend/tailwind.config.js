/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        serif: ['var(--font-serif)', 'Georgia', 'serif'],
      },
      colors: {
        brand: {
          DEFAULT: '#4B2E2A',
          light: '#7A3E2F',
          lighter: '#8B5A4A',
          lightest: '#A67C6B',
        },
        bg: {
          DEFAULT: '#FBF7F2',
          card: '#FFFFFF',
          muted: '#F5F1EB',
        },
        border: {
          DEFAULT: '#E8E3DC',
          strong: '#D4C9BC',
        },
        text: {
          DEFAULT: '#2C2418',
          muted: '#6B5E52',
          subtle: '#9B8E80',
        },
        risk: {
          low: '#16A34A',
          'low-bg': '#DCFCE7',
          medium: '#D97706',
          'medium-bg': '#FEF3C7',
          high: '#DC2626',
          'high-bg': '#FEE2E2',
          critical: '#991B1B',
          'critical-bg': '#FECACA',
        },
        // Keep primary for backward compatibility, map to brand
        primary: {
          50: '#F5F1EB',
          100: '#E8E3DC',
          200: '#D4C9BC',
          300: '#A67C6B',
          400: '#8B5A4A',
          500: '#7A3E2F',
          600: '#4B2E2A',
          700: '#3D241F',
          800: '#2E1B17',
          900: '#1F120F',
        },
      },
    },
  },
  plugins: [],
};
