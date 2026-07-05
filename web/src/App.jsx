import { useState } from 'react'
import Nav from './components/Nav.jsx'
import ThemeToggle from './components/ThemeToggle.jsx'
import IntroView from './views/IntroView.jsx'
import PredictionsView from './views/PredictionsView.jsx'
import SimulationView from './views/SimulationView.jsx'
import HistoryView from './views/HistoryView.jsx'
import ChallengeView from './views/ChallengeView.jsx'

// Coquille de l'application : marque + bascule de thème + navigation.
// Chaque vue charge ses propres données à la demande (navigation instantanée).
export default function App() {
  const [view, setView] = useState('home')   // page d'accueil par défaut

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      {/* Marque + thème */}
      <header className="mb-6 flex items-center justify-between gap-3">
        <button onClick={() => setView('home')} className="flex items-center gap-3 text-left">
          <span className="text-3xl">🎾</span>
          <div>
            <h1 className="bg-gradient-to-r from-brand to-fuchsia-400 bg-clip-text text-2xl
              font-extrabold text-transparent sm:text-3xl">
              Tennis Predictor
            </h1>
            <p className="text-sm text-lo">Grand Chelem · probabilités &amp; historique</p>
          </div>
        </button>
        <ThemeToggle />
      </header>

      <Nav view={view} onChange={setView} />

      {/* On MONTE une seule vue à la fois (rendu léger). */}
      {view === 'home' && <IntroView onNavigate={setView} />}
      {view === 'predictions' && <PredictionsView />}
      {view === 'simulation' && <SimulationView />}
      {view === 'history' && <HistoryView />}
      {view === 'challenge' && <ChallengeView />}

      <footer className="mt-10 text-center text-xs text-lo">
        Données : tennis-data.co.uk · Modèle réentraîné automatiquement via GitHub Actions
      </footer>
    </div>
  )
}
