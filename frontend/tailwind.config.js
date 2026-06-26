/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        'navy-deep': '#0a1628',
        'navy-card': '#0f2044',
        'navy-light': '#163a6e',
        'blue-accent': '#4fc3f7',
        'gold': '#f0c14b',
        'gold-soft': '#c9a227',
        'red-up': '#ff5252',
        'green-down': '#69f0ae',
        'yellow-warn': '#ffd740',
        'text-primary': '#e8e8e8',
        'text-secondary': '#8899aa',
        'text-muted': '#556677',
      },
      fontFamily: {
        sans: ['-apple-system', 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
