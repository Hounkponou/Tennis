import { useEffect, useState } from 'react'
import { loadJSON } from '../lib/data.js'

// Cartes de menu de la page d'accueil.
const MENUS = [
  { id: 'predictions', icon: '🔮', title: 'Matchs à venir',
    desc: 'Les probabilités de victoire des prochains matchs du Grand Chelem.' },
  { id: 'simulation', icon: '⚔️', title: 'Simulation',
    desc: 'Fais s’affronter deux joueurs et obtiens les probabilités en temps réel.' },
  { id: 'history', icon: '📚', title: 'Historique',
    desc: 'Tous les résultats passés, filtrables par championnat, année et joueur.' },
  { id: 'challenge', icon: '🎯', title: 'Challenge',
    desc: 'Le taux de réussite du modèle, vérifié match après match.' },
  { id: 'tracking', icon: '📊', title: 'Suivi des prédictions',
    desc: 'Résultat prédit vs résultat réel des matchs publiés, et taux de réussite.' },
]

// Page d'introduction : présentation + accès aux menus + quelques chiffres.
export default function IntroView({ onNavigate }) {
  const [meta, setMeta] = useState(null)
  const [pred, setPred] = useState(null)

  useEffect(() => {
    loadJSON('meta.json').then(setMeta).catch(() => {})
    loadJSON('predictions.json').then(setPred).catch(() => {})
  }, [])

  const acc = pred?.model_metrics?.accuracy
  const stats = [
    { value: meta ? meta.n_matches.toLocaleString('fr-FR') : '—', label: 'matchs historiques' },
    { value: meta ? meta.n_players.toLocaleString('fr-FR') : '—', label: 'joueurs suivis' },
    { value: acc != null ? `${Math.round(acc * 100)}%` : '—', label: 'précision du modèle' },
    { value: '4', label: 'tournois du Grand Chelem' },
  ]

  return (
    <div className="space-y-8">
      {/* Hero */}
      <section className="glass p-6 sm:p-8">
        <h2 className="text-2xl font-extrabold sm:text-3xl">
          Prédisez les matchs du <span className="text-brand">Grand Chelem</span>
        </h2>
        <p className="mt-2 max-w-2xl text-mid">
          Un modèle de machine learning entraîné sur plus de 20&nbsp;ans de résultats ATP
          &amp; WTA estime les probabilités de victoire. Explore les prédictions à venir,
          simule tes propres affiches, plonge dans l’historique et mesure la fiabilité du modèle.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <button onClick={() => onNavigate('predictions')}
            className="rounded-xl bg-brand px-5 py-2.5 text-sm font-semibold text-slate-900">
            Voir les prédictions
          </button>
          <button onClick={() => onNavigate('simulation')}
            className="glass hover-surface rounded-xl px-5 py-2.5 text-sm font-semibold">
            Lancer une simulation
          </button>
        </div>
      </section>

      {/* Chiffres clés */}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="glass p-4 text-center">
            <div className="text-2xl font-bold text-brand">{s.value}</div>
            <div className="mt-1 text-xs text-lo">{s.label}</div>
          </div>
        ))}
      </section>

      {/* Menus */}
      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-lo">Menus</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {MENUS.map((m) => (
            <button key={m.id} onClick={() => onNavigate(m.id)}
              className="glass hover-surface flex items-start gap-4 p-5 text-left">
              <span className="text-3xl">{m.icon}</span>
              <span>
                <span className="block font-semibold">{m.title}</span>
                <span className="mt-1 block text-sm text-mid">{m.desc}</span>
              </span>
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}
