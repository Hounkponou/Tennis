/** @type {import('tailwindcss').Config} */
// Mode sombre natif ('class' -> on ajoute la classe `dark` sur <html>).
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Palette d'accent (dégradé cyan -> violet) pour les éléments actifs.
        brand: { DEFAULT: '#22d3ee', deep: '#7c3aed' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
