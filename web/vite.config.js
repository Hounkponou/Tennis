import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base: './' -> chemins relatifs, l'app fonctionne aussi bien sur Vercel que
// sur GitHub Pages ou en ouverture locale du dossier dist/.
export default defineConfig({
  plugins: [react()],
  base: './',
})
