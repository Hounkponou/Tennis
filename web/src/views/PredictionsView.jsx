import { useEffect, useMemo, useState } from 'react'
import { loadJSON } from '../lib/data.js'
import MatchCard from '../components/MatchCard.jsx'
import { Segmented, Select } from '../components/Field.jsx'

// Onglet "Prédictions à venir" : cartes de matchs prédits + filtres.
export default function PredictionsView() {
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('loading')
  const [tour, setTour] = useState('')          // '' = tous
  const [tournament, setTournament] = useState('')

  useEffect(() => {
    loadJSON('predictions.json')
      .then((d) => { setData(d); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [])

  const tournaments = useMemo(
    () => [...new Set((data?.matches ?? []).map((m) => m.tournament))].sort(),
    [data],
  )

  const matches = useMemo(() => {
    if (!data) return []
    return data.matches.filter(
      (m) => (!tour || m.tour === tour) && (!tournament || m.tournament === tournament),
    )
  }, [data, tour, tournament])

  if (status === 'loading') return <Skeleton />
  if (status === 'error')
    return <Empty text="Aucune prédiction. Lance : python -m ml.predict" />

  const met = data.model_metrics ?? {}
  return (
    <div>
      {/* Bandeau modèle : transparence sur la performance */}
      <div className="mb-4 flex flex-wrap gap-2 text-xs">
        <Badge label="Modèle" value={data.model_version} />
        <Badge label="Précision test" value={met.accuracy != null ? `${Math.round(met.accuracy * 100)}%` : '—'} />
        <Badge label="ROC-AUC" value={met.roc_auc ?? '—'} />
      </div>

      {/* Filtres */}
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <Segmented
          value={tour}
          onChange={setTour}
          options={[{ value: '', label: 'Tous' }, { value: 'ATP', label: 'ATP' }, { value: 'WTA', label: 'WTA' }]}
        />
        <Select label="Tournoi" value={tournament} onChange={setTournament}
                options={tournaments} allLabel="Tous les tournois" />
      </div>

      {matches.length === 0
        ? <Empty text="Aucun match ne correspond aux filtres." />
        : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {matches.map((m) => <MatchCard key={m.id} match={m} />)}
          </div>
        )}
    </div>
  )
}

function Badge({ label, value }) {
  return (
    <span className="glass px-3 py-1">
      <span className="text-lo">{label} : </span>
      <span className="font-semibold text-hi">{value}</span>
    </span>
  )
}
function Skeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {Array.from({ length: 4 }).map((_, i) => <div key={i} className="glass h-40 animate-pulse" />)}
    </div>
  )
}
function Empty({ text }) {
  return <p className="glass p-6 text-center text-lo">{text}</p>
}
