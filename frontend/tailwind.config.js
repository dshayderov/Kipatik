/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        gh: {
          bg: '#f6f8fa',
          border: '#d0d7de',
          text: '#1f2328',
          secondary: '#636c76',
          link: '#0969da',
          success: '#1f883d',
        }
      }
    },
  },
  plugins: [],
}
