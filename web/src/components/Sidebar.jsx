import ThemeToggle from './ThemeToggle.jsx'

const TABS = [
  { id: 'home', label: 'Accueil', icon: '🏠' },
  { id: 'predictions', label: 'Matchs à venir', icon: '🔮' },
  { id: 'simulation', label: 'Simulation', icon: '⚔️' },
  { id: 'history', label: 'Historique', icon: '📚' },
  { id: 'challenge', label: 'Challenge', icon: '🎯' },
  { id: 'tracking', label: 'Suivi', icon: '📊' },
]

/**
 * Menu latéral (sidebar).
 * - Desktop (md+) : fixe, toujours visible ; le contenu est décalé (md:ml-64).
 * - Mobile : hors-champ, s'ouvre en tiroir par-dessus (avec fond assombri).
 */
export default function Sidebar({ view, onChange, open, onClose }) {
  return (
    <>
      {/* Fond assombri sur mobile quand le tiroir est ouvert */}
      {open && (
        <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={onClose} />
      )}

      <aside
        className={`glass !rounded-none fixed inset-y-0 left-0 z-40 flex w-64 flex-col
          p-4 transition-transform duration-200
          ${open ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0`}
      >
        {/* Marque */}
        <button onClick={() => onChange('home')}
          className="mb-6 flex items-center gap-3 text-left">
          <span className="text-3xl">🎾</span>
          <span className="bg-gradient-to-r from-brand to-fuchsia-400 bg-clip-text
            text-xl font-extrabold text-transparent">
            Tennis Predictor
          </span>
        </button>

        {/* Navigation */}
        <nav className="flex-1 space-y-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => onChange(t.id)}
              className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5
                text-sm font-semibold transition
                ${view === t.id ? 'bg-brand text-slate-900' : 'text-mid hover-surface'}`}
            >
              <span className="text-lg">{t.icon}</span>
              <span>{t.label}</span>
            </button>
          ))}
        </nav>

        {/* Pied : thème */}
        <div className="mt-4 flex items-center justify-between border-t pt-4"
             style={{ borderColor: 'var(--c-br)' }}>
          <span className="text-xs text-lo">Thème</span>
          <ThemeToggle />
        </div>
      </aside>
    </>
  )
}
