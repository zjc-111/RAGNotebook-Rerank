/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        heading: ['Playfair Display', 'Noto Serif SC', 'Songti SC', 'serif'],
        body: ['Noto Sans SC', 'PingFang SC', 'SF Pro Display', 'Helvetica Neue', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Consolas', 'monospace'],
      },
      letterSpacing: {
        display: '-0.03em',
        heading: '-0.02em',
        label: '0.14em',
      },
      colors: {
        bg: {
          DEFAULT: '#F7F4EF',
          secondary: '#F1EDE6',
          tertiary: '#EBE6DC',
        },
        card: {
          DEFAULT: '#FFFFFF',
          hover: '#FAF7F2',
        },
        text: {
          DEFAULT: '#1C1B19',
          secondary: '#6B6A66',
          tertiary: '#9C9992',
          placeholder: '#BEB9AE',
        },
        border: {
          DEFAULT: '#E2DCD1',
          light: '#ECE7DD',
        },
        divider: '#E8E2D7',
        accent: {
          DEFAULT: '#B4463C',
          bg: '#F6E9E6',
        },
        ink: '#1C1B19',
        success: {
          DEFAULT: '#3F5E4B',
          bg: '#EBF0EB',
        },
        danger: {
          DEFAULT: '#8E3B36',
          bg: '#F8E9E7',
        },
        warning: {
          DEFAULT: '#8A6A34',
          bg: '#F6EFDF',
        },
      },
      spacing: {
        'xs': '4px',
        'sm': '8px',
        'md': '16px',
        'lg': '24px',
        'xl': '32px',
        '2xl': '48px',
        '3xl': '64px',
      },
      borderRadius: {
        sm: '0px',
        md: '2px',
        lg: '4px',
      },
      lineHeight: {
        tight: '1.3',
        normal: '1.6',
        loose: '1.8',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
