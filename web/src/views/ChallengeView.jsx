import { useEffect, useMemo, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { loadJSON } from '../lib/data.js'
import { Segmented } from '../components/Field.jsx'

// Onglet "Challenge" : mesure, après coup, le taux de réussite des prédictions.
export default function ChallengeView() {
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('loading')
  const [filter, setFilter] = useState('')   // filtre circuit des matchs récents

  useEffect(() => {
    loadJSON('challenge.json')
      .then((d) => { setData(d); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [])

  const recent = useMemo(() => {
    if (!data) return []
    return data.recent.filter((m) => !filter || m.tour === filter)
  }, [data, filter])

  if (status === 'loading') return <p className="glass p-6 text-center text-lo">Chargement…</p>
  if (status === 'error') return <p className="glass p-6 text-center text-lo">Challenge indisponible.</p>

  const chart = data.by_year.map((y) => ({ year: y.year, acc: Math.round(y.accuracy * 100) }))

  return (
    <div className="space-y-5">
      {/* Chiffres de tête */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Kpi big value={pct(data.holdout_accuracy)} label="Précision hors échantillon"
             hint="Sur des matchs jamais vus à l'entraînement (chiffre honnête)." />
        <Kpi value={pct(data.backtest_accuracy)} label="Réussite sur tout l'historique"
             hint={`${data.n_matches.toLocaleString('fr-FR')} matchs rejoués`} />
        <Kpi value={bestSurface(data.by_surface)} label="Meilleure surface" />
      </div>

      {/* Graphique : précision par année (Recharts) */}
      <div className="glass p-4">
        <h3 className="mb-3 text-sm font-semibold text-mid">Taux de réussite par année</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--c-br)" vertical={false} />
              <XAxis dataKey="year" tick={{ fill: 'var(--c-lo)', fontSize: 11 }}
                     interval={2} axisLine={false} tickLine={false} />
              <YAxis domain={[40, 85]} tick={{ fill: 'var(--c-lo)', fontSize: 11 }}
                     axisLine={false} tickLine={false} unit="%" />
              <Tooltip
                cursor={{ fill: 'var(--c-surf2)' }}
                contentStyle={{ background: 'var(--c-page)', border: '1px solid var(--c-br)',
                  borderRadius: 12, color: 'var(--c-hi)' }}
                formatter={(v) => [`${v}%`, 'Réussite']} />
              <Bar dataKey="acc" fill="#22d3ee" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Ventilation par surface */}
      <div className="grid grid-cols-3 gap-3">
        {data.by_surface.map((s) => (
          <div key={s.surface} className="glass p-3 text-center">
            <div className="text-lg font-bold text-brand">{pct(s.accuracy)}</div>
            <div className="text-xs text-lo">{s.surface} · {s.n.toLocaleString('fr-FR')}</div>
          </div>
        ))}
      </div>

      {/* Matchs récents : le modèle avait-il raison ? */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-mid">Vérification match par match</h3>
          <Segmented value={filter} onChange={setFilter}
            options={[{ value: '', label: 'Tous' }, { value: 'ATP', label: 'ATP' }, { value: 'WTA', label: 'WTA' }]} />
        </div>
        <div className="space-y-2">
          {recent.map((m, i) => <ChallengeRow key={i} m={m} />)}
        </div>
      </div>

      <p className="text-center text-xs text-lo">
        « Réussite » = le modèle donnait le vrai vainqueur favori (probabilité ≥ 50 %).
      </p>
    </div>
  )
}

const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`)
const bestSurface = (arr) =>
  arr && arr.length ? [...arr].sort((a, b) => b.accuracy - a.accuracy)[0].surface : '—'

function Kpi({ value, label, hint, big }) {
  return (
    <div className="glass p-4">
      <div className={`font-bold text-brand ${big ? 'text-4xl' : 'text-3xl'}`}>{value}</div>
      <div className="mt-1 text-sm font-medium text-hi">{label}</div>
      {hint && <div className="mt-0.5 text-xs text-lo">{hint}</div>}
    </div>
  )
}

function ChallengeRow({ m }) {
  return (
    <div className="glass flex items-center gap-3 px-4 py-2.5 text-sm">
      <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs
        ${m.correct ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
        {m.correct ? '✓' : '✗'}
      </span>
      {/* Bloc central : date + tournoi au-dessus, affiche en dessous (tronquée). */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs text-lo">
          <span className="shrink-0 whitespace-nowrap">{m.date}</span>
          <span className="truncate">{m.tournament}</span>
        </div>
        <div className="truncate">
          <span className="font-semibold text-emerald-300">{m.winner}</span>
          <span className="mx-1 text-lo">déf.</span>
          <span className="text-mid">{m.loser}</span>
        </div>
      </div>
      {/* Confiance du modèle envers le vrai vainqueur */}
      <div className="shrink-0 text-right text-xs tabular-nums text-lo">
        <div className="font-semibold text-hi">{Math.round(m.prob_winner * 100)}%</div>
        <div>confiance</div>
      </div>
    </div>
  )
}
