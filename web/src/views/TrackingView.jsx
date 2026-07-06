import { useEffect, useMemo, useState } from 'react'
import { loadJSON } from '../lib/data.js'
import { Segmented } from '../components/Field.jsx'

// Onglet "Suivi" : les prédictions publiées confrontées au résultat réel.
export default function TrackingView() {
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('loading')
  const [filter, setFilter] = useState('') // '' tous | pending | resolved

  useEffect(() => {
    loadJSON('tracking.json')
      .then((d) => { setData(d); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [])

  const entries = useMemo(() => {
    if (!data) return []
    return data.entries.filter((e) => !filter || e.status === filter)
  }, [data, filter])

  if (status === 'loading') return <p className="glass p-6 text-center text-lo">Chargement…</p>
  if (status === 'error') return <p className="glass p-6 text-center text-lo">Suivi indisponible.</p>

  const rate = data.success_rate != null ? `${Math.round(data.success_rate * 100)}%` : '—'

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold">Suivi des prédictions</h2>
        <p className="text-sm text-lo">Résultat prédit par le modèle vs résultat réel.</p>
      </div>

      {/* Chiffres de tête */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="glass p-4">
          <div className="text-4xl font-bold text-brand">{rate}</div>
          <div className="mt-1 text-sm font-medium text-hi">Taux de réussite</div>
          <div className="text-xs text-lo">{data.n_correct} bonnes sur {data.n_resolved} résolues</div>
        </div>
        <div className="glass p-4">
          <div className="text-3xl font-bold">{data.n_resolved}</div>
          <div className="mt-1 text-sm text-lo">prédictions vérifiées</div>
        </div>
        <div className="glass p-4">
          <div className="text-3xl font-bold text-amber-400">{data.n_pending}</div>
          <div className="mt-1 text-sm text-lo">en attente de résultat</div>
        </div>
      </div>

      {/* Filtre par statut */}
      <Segmented value={filter} onChange={setFilter}
        options={[
          { value: '', label: 'Toutes' },
          { value: 'pending', label: 'À venir' },
          { value: 'resolved', label: 'Vérifiées' },
        ]} />

      {/* Liste */}
      <div className="space-y-2">
        {entries.map((e) => <TrackRow key={e.id} e={e} />)}
      </div>

      <p className="text-center text-xs text-lo">
        Une prédiction est « bonne » si le vainqueur prédit = vainqueur réel.
        Les matchs à venir se vérifient automatiquement une fois joués.
      </p>
    </div>
  )
}

function TrackRow({ e }) {
  const pending = e.status === 'pending'
  const prob = Math.round(e.predicted_prob * 100)

  // Pastille de statut : ⏳ en attente, ✓ correct, ✗ raté.
  const badge = pending
    ? { txt: '⏳', cls: 'bg-amber-500/20 text-amber-400' }
    : e.correct
      ? { txt: '✓', cls: 'bg-emerald-500/20 text-emerald-400' }
      : { txt: '✗', cls: 'bg-rose-500/20 text-rose-400' }

  return (
    <div className="glass flex items-center gap-3 px-4 py-2.5 text-sm">
      <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full
        text-xs ${badge.cls}`}>{badge.txt}</span>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs text-lo">
          <span className="shrink-0 whitespace-nowrap">{e.date}</span>
          <span className="truncate">{e.tournament}</span>
        </div>
        <div className="truncate">
          <span className="text-lo">Prédit </span>
          <span className="font-semibold text-hi">{e.predicted_winner}</span>
          <span className="text-lo"> ({prob}%)</span>
          {!pending && (
            <>
              <span className="text-lo"> · Réel </span>
              <span className={`font-semibold ${e.correct ? 'text-emerald-300' : 'text-rose-400'}`}>
                {e.actual_winner}
              </span>
            </>
          )}
        </div>
      </div>

      {pending && <span className="shrink-0 text-xs text-amber-400">en attente</span>}
    </div>
  )
}
