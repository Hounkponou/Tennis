import { useEffect, useMemo, useState } from 'react'
import { loadJSON } from '../lib/data.js'
import { loadSim, predictProb } from '../lib/predict.js'
import { Segmented, Select } from '../components/Field.jsx'
import Gauge from '../components/Gauge.jsx'

const ROUNDS = ['1st Round', '2nd Round', '3rd Round', '4th Round',
  'Quarterfinals', 'Semifinals', 'The Final']

// Surface par défaut selon le tournoi (repère réaliste, restant modifiable).
const SURFACE_OF = { Wimbledon: 'Grass', 'French Open': 'Clay' }

export default function SimulationView() {
  const [sim, setSim] = useState(null)      // { model, players }
  const [meta, setMeta] = useState(null)
  const [status, setStatus] = useState('loading')

  const [tour, setTour] = useState('ATP')
  const [p1, setP1] = useState('')
  const [p2, setP2] = useState('')
  const [tournament, setTournament] = useState('Wimbledon')
  const [surface, setSurface] = useState('Grass')
  const [round, setRound] = useState('The Final')

  useEffect(() => {
    Promise.all([loadSim(), loadJSON('meta.json')])
      .then(([s, m]) => { setSim(s); setMeta(m); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [])

  // Liste des joueurs du circuit sélectionné, triés par classement.
  const playerNames = useMemo(() => {
    if (!sim) return []
    return Object.entries(sim.players)
      .filter(([, p]) => p.tour === tour)
      .sort((a, b) => (a[1].rank ?? 9999) - (b[1].rank ?? 9999))
      .map(([name]) => name)
  }, [sim, tour])

  // Changer de tournoi ajuste la surface par défaut.
  function pickTournament(t) {
    setTournament(t)
    setSurface(SURFACE_OF[t] ?? 'Hard')
  }

  const ready = sim && p1 && p2 && p1 !== p2
    && sim.players[p1] && sim.players[p2]

  const prob1 = useMemo(() => {
    if (!ready) return null
    return predictProb(sim.model, sim.players, p1, p2, { tournament, surface, round })
  }, [ready, sim, p1, p2, tournament, surface, round])

  if (status === 'loading') return <p className="glass p-6 text-center text-lo">Chargement du moteur…</p>
  if (status === 'error') return <p className="glass p-6 text-center text-lo">Données de simulation indisponibles.</p>

  return (
    <div className="space-y-5">
      {/* Contexte du match */}
      <div className="glass space-y-3 p-4">
        <Segmented value={tour} onChange={(t) => { setTour(t); setP1(''); setP2('') }}
          options={[{ value: 'ATP', label: 'ATP (H)' }, { value: 'WTA', label: 'WTA (F)' }]} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Select label="Tournoi" value={tournament} onChange={pickTournament}
                  options={meta?.tournaments ?? []} />
          <Select label="Surface" value={surface} onChange={setSurface}
                  options={meta?.surfaces ?? ['Hard', 'Clay', 'Grass']} />
          <Select label="Tour" value={round} onChange={setRound} options={ROUNDS} />
        </div>
      </div>

      {/* Sélection des joueurs */}
      <datalist id="players-list">
        {playerNames.map((n) => <option key={n} value={n} />)}
      </datalist>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <PlayerPicker label="Joueur 1" value={p1} onChange={setP1} />
        <PlayerPicker label="Joueur 2" value={p2} onChange={setP2} />
      </div>

      {/* Résultat en temps réel */}
      {p1 && p2 && p1 === p2 && (
        <p className="text-center text-sm text-amber-400">Choisis deux joueurs différents.</p>
      )}
      {ready && prob1 != null && (
        <Result sim={sim} p1={p1} p2={p2} prob1={prob1}
                ctx={{ tournament, surface, round }} />
      )}
      {(!p1 || !p2) && (
        <p className="glass p-6 text-center text-lo">
          Sélectionne deux joueurs pour voir les probabilités.
        </p>
      )}
    </div>
  )
}

function PlayerPicker({ label, value, onChange }) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="text-lo">{label}</span>
      <input
        list="players-list"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Rechercher un joueur…"
        className="glass rounded-lg px-3 py-2 text-sm text-hi outline-none
          focus:ring-1 focus:ring-brand"
      />
    </label>
  )
}

// Affiche la jauge + les deux fiches de forme des joueurs.
function Result({ sim, p1, p2, prob1, ctx }) {
  const prob2 = 1 - prob1
  const p1Fav = prob1 >= prob2
  const favProb = Math.max(prob1, prob2) * 100

  return (
    <div className="glass space-y-4 p-4">
      <div className="flex items-center justify-center gap-6">
        <div className="text-center">
          <div className={`text-3xl font-bold tabular-nums ${p1Fav ? 'text-brand' : 'text-mid'}`}>
            {Math.round(prob1 * 100)}%
          </div>
          <div className="max-w-[9rem] truncate text-sm text-mid">{p1}</div>
        </div>
        <Gauge value={favProb} color={p1Fav ? '#22d3ee' : '#d946ef'} />
        <div className="text-center">
          <div className={`text-3xl font-bold tabular-nums ${!p1Fav ? 'text-fuchsia-400' : 'text-mid'}`}>
            {Math.round(prob2 * 100)}%
          </div>
          <div className="max-w-[9rem] truncate text-sm text-mid">{p2}</div>
        </div>
      </div>

      <div className="flex h-2 overflow-hidden rounded-full bg-slate-700/50">
        <div className="bg-gradient-to-r from-brand to-cyan-400" style={{ width: `${prob1 * 100}%` }} />
        <div className="bg-gradient-to-r from-fuchsia-500 to-brand-deep" style={{ width: `${prob2 * 100}%` }} />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FormCard player={sim.players[p1]} name={p1} ctx={ctx} />
        <FormCard player={sim.players[p2]} name={p2} ctx={ctx} />
      </div>
    </div>
  )
}

// Fiche "forme historique" d'un joueur (répond au besoin d'exposer la forme).
function FormCard({ player, name, ctx }) {
  const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`)
  return (
    <div className="rounded-xl surface p-3 text-sm">
      <div className="mb-2 flex items-center gap-2">
        <span className="font-semibold">{name}</span>
        {player.rank && <span className="rounded surface-2 px-1.5 py-0.5 text-[10px]">#{player.rank}</span>}
      </div>
      <dl className="grid grid-cols-2 gap-y-1 text-xs text-mid">
        <Stat label="Matchs joués" value={player.matches} />
        <Stat label="Victoires (global)" value={pct(player.wr_global)} />
        <Stat label={`Surface ${ctx.surface}`} value={pct(player.wr_surface?.[ctx.surface])} />
        <Stat label={ctx.tournament} value={pct(player.wr_tourney?.[ctx.tournament])} />
        <Stat label="Forme 5 derniers" value={pct(player.wr5)} />
        <Stat label="Forme 10 derniers" value={pct(player.wr10)} />
      </dl>
    </div>
  )
}
function Stat({ label, value }) {
  return (
    <>
      <dt className="text-lo">{label}</dt>
      <dd className="text-right font-medium text-hi">{value}</dd>
    </>
  )
}
