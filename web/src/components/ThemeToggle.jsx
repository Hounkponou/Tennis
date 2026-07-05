import { useTheme } from '../lib/theme.js'

// Bouton de bascule clair/sombre (persistant).
export default function ThemeToggle() {
  const { dark, toggle } = useTheme()
  return (
    <button
      onClick={toggle}
      title={dark ? 'Passer en mode clair' : 'Passer en mode sombre'}
      aria-label="Basculer le thème"
      className="glass hover-surface flex h-10 w-10 items-center justify-center text-lg"
    >
      {dark ? '☀️' : '🌙'}
    </button>
  )
}
