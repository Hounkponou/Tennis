import { useEffect, useMemo, useState } from 'react'
import { loadJSON } from '../lib/data.js'
import { Segmented, Select } from '../components/Field.jsx'

const PAGE = 40  // nombre de matchs affichés par palier (perf sur 23k lignes)

// Onglet "Historique" : résultats passés, filtrables par championnat, année,
// surface, tour et joueur. history.json n'est chargé QUE quand on ouvre l'onglet.
export default function HistoryView() {
  const [rows, setRows] = useState(null)
  const [meta, setMeta] = useState(null)
  const [status, setStatus] = useState('loading')

  const [tour, setTour] = useState('')
  const [tournament, setTournament] = useState('')
  const [year, setYear] = useState('')
  const [surface, setSurface] = useState('')
  const [q, setQ] = useState('')            // recherche joueur
  const [sort, setSort] = useState('recent')
  const [limit, setLimit] = useState(PAGE)

  // Ordre des tours, pour un tri « avancement dans le tournoi » cohérent.
  const ROUND_RANK = {
    '1st Round': 1, '2nd Round': 2, '3rd Round': 3, '4th Round': 4,
    Quarterfinals: 5, Semifinals: 6, 'The Final': 7,
  }

  useEffect(() => {
    Promise.all([loadJSON('history.json'), loadJSON('meta.json')])
      .then(([h, m]) => { setRows(h); setMeta(m); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [])

  // Filtrage mémoïsé. On réinitialise la pagination à chaque changement.
  const filtered = useMemo(() => {
    if (!rows) return []
    const needle = q.trim().toLowerCase()
    return rows.filter((r) =>
      (!tour || r.tour === tour) &&
      (!tournament || r.tournament === tournament) &&
      (!year || String(r.year) === year) &&
      (!surface || r.surface === surface) &&
      (!needle || r.winner.toLowerCase().includes(needle) || r.loser.toLowerCase().includes(needle)),
    )
  }, [rows, tour, tournament, year, surface, q])

  // Tri mémoïsé, appliqué après le filtrage.
  const sorted = useMemo(() => {
    const arr = [...filtered]
    if (sort === 'recent') arr.sort((a, b) => b.date.localeCompare(a.date))
    else if (sort === 'ancien') arr.sort((a, b) => a.date.localeCompare(b.date))
    else if (sort === 'tournoi')
      arr.sort((a, b) => a.tournament.localeCompare(b.tournament) || b.date.localeCompare(a.date))
    else if (sort === 'tour')
      arr.sort((a, b) => (ROUND_RANK[b.round] ?? 0) - (ROUND_RANK[a.round] ?? 0))
    return arr
  }, [filtered, sort])

  useEffect(() => { setLimit(PAGE) }, [tour, tournament, year, surface, q, sort])

  if (status === 'loading') return <p className="glass p-6 text-center text-lo">Chargement de l'historique…</p>
  if (status === 'error') return <p className="glass p-6 text-center text-lo">Historique indisponible.</p>

  const visible = sorted.slice(0, limit)

  return (
    <div className="space-y-4">
      {/* Filtres */}
      <div className="glass space-y-3 p-4">
        <Segmented value={tour} onChange={setTour}
          options={[{ value: '', label: 'Tous' }, { value: 'ATP', label: 'ATP' }, { value: 'WTA', label: 'WTA' }]} />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Select label="Championnat" value={tournament} onChange={setTournament}
                  options={meta?.tournaments ?? []} allLabel="Tous" />
          <Select label="Année" value={year} onChange={setYear}
                  options={(meta?.years ?? []).map(String)} allLabel="Toutes" />
          <Select label="Surface" value={surface} onChange={setSurface}
                  options={meta?.surfaces ?? []} allLabel="Toutes" />
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-lo">Joueur</span>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nom…"
              className="glass rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-brand" />
          </label>
        </div>
      </div>

      {/* Compteur + tri */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-lo">
          <span className="font-semibold text-hi">{sorted.length.toLocaleString('fr-FR')}</span> match(s) trouvé(s)
        </p>
        <label className="flex items-center gap-2 text-xs text-lo">
          Trier :
          <select value={sort} onChange={(e) => setSort(e.target.value)}
            className="glass rounded-lg px-3 py-2 text-sm text-hi outline-none focus:ring-1 focus:ring-brand">
            <option value="recent">Plus récent</option>
            <option value="ancien">Plus ancien</option>
            <option value="tournoi">Par championnat</option>
            <option value="tour">Par tour</option>
          </select>
        </label>
      </div>

      {/* Liste des résultats */}
      <div className="space-y-2">
        {visible.map((r, i) => <ResultRow key={i} r={r} />)}
      </div>

      {limit < filtered.length && (
        <button onClick={() => setLimit((l) => l + PAGE)}
          className="glass w-full py-3 text-sm font-medium text-hi hover-surface">
          Afficher plus ({filtered.length - limit} restant(s))
        </button>
      )}
      {filtered.length === 0 && <p className="glass p-6 text-center text-lo">Aucun résultat.</p>}
    </div>
  )
}

const SURFACE_DOT = { Grass: 'bg-emerald-400', Clay: 'bg-orange-400', Hard: 'bg-sky-400' }

function ResultRow({ r }) {
  return (
    <div className="glass flex items-center gap-3 px-4 py-2.5 text-sm">
      <div className="w-20 shrink-0 text-xs text-lo">{r.date}</div>
      <div className="hidden w-40 shrink-0 items-center gap-2 sm:flex">
        <span className={`h-2 w-2 rounded-full ${SURFACE_DOT[r.surface] ?? 'bg-slate-400'}`} />
        <span className="truncate text-xs text-mid">{r.tournament}</span>
      </div>
      <div className="w-16 shrink-0 text-xs text-lo">{r.round}</div>
      <div className="min-w-0 flex-1">
        <span className="font-semibold text-emerald-300">{r.winner}</span>
        <span className="mx-1 text-lo">déf.</span>
        <span className="text-mid">{r.loser}</span>
      </div>
      <div className="hidden shrink-0 text-xs tabular-nums text-lo sm:block">{r.score}</div>
    </div>
  )
}
