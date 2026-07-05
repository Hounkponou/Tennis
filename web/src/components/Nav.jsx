// Barre de navigation entre les 3 menus. Onglets larges = tactile (mobile-first).
const TABS = [
  { id: 'home', label: 'Accueil', icon: '🏠' },
  { id: 'predictions', label: 'À venir', icon: '🔮' },
  { id: 'simulation', label: 'Simulation', icon: '⚔️' },
  { id: 'history', label: 'Historique', icon: '📚' },
  { id: 'challenge', label: 'Challenge', icon: '🎯' },
]

export default function Nav({ view, onChange }) {
  return (
    <nav className="glass mb-6 flex gap-1 p-1">
      {TABS.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-3 py-2
            text-sm font-semibold transition
            ${view === t.id
              ? 'bg-brand text-slate-900'
              : 'text-mid hover-surface'}`}
        >
          <span>{t.icon}</span>
          <span className="hidden sm:inline">{t.label}</span>
        </button>
      ))}
    </nav>
  )
}
