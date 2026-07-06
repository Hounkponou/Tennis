import { useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import IntroView from './views/IntroView.jsx'
import PredictionsView from './views/PredictionsView.jsx'
import SimulationView from './views/SimulationView.jsx'
import HistoryView from './views/HistoryView.jsx'
import ChallengeView from './views/ChallengeView.jsx'

// Coquille : sidebar (menu) à gauche + zone de contenu. Une seule vue montée
// à la fois. Sur mobile, la sidebar s'ouvre en tiroir via le bouton ☰.
export default function App() {
  const [view, setView] = useState('home')
  const [menuOpen, setMenuOpen] = useState(false)

  // Naviguer ferme aussi le tiroir mobile.
  const go = (v) => { setView(v); setMenuOpen(false) }

  return (
    <div>
      <Sidebar view={view} onChange={go} open={menuOpen} onClose={() => setMenuOpen(false)} />

      <div className="md:ml-64">
        {/* Barre supérieure mobile (accès au menu) */}
        <div className="sticky top-0 z-20 flex items-center gap-3 border-b px-4 py-3
          backdrop-blur-sm md:hidden"
          style={{ borderColor: 'var(--c-br)', background: 'var(--c-surf)' }}>
          <button onClick={() => setMenuOpen(true)} aria-label="Ouvrir le menu"
            className="text-2xl leading-none">☰</button>
          <span className="bg-gradient-to-r from-brand to-fuchsia-400 bg-clip-text
            font-extrabold text-transparent">Tennis Predictor</span>
        </div>

        <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
          {view === 'home' && <IntroView onNavigate={go} />}
          {view === 'predictions' && <PredictionsView />}
          {view === 'simulation' && <SimulationView />}
          {view === 'history' && <HistoryView />}
          {view === 'challenge' && <ChallengeView />}

          <footer className="mt-10 text-center text-xs text-lo">
            Données : tennis-data.co.uk &amp; tennisexplorer.com · Modèle réentraîné via GitHub Actions
          </footer>
        </main>
      </div>
    </div>
  )
}
