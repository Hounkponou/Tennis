import Gauge from './Gauge.jsx'

// Couleur d'accent selon la surface (repère visuel immédiat).
const SURFACE_STYLE = {
  Grass: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  Clay: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  Hard: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
}

// Pastilles de forme récente : 🟢 victoire / 🔴 défaite (plus récent à droite).
function FormDots({ form }) {
  if (!form || form.length === 0) return <span className="text-lo text-xs">—</span>
  return (
    <div className="flex gap-1">
      {form.map((r, i) => (
        <span key={i}
          className={`h-2 w-2 rounded-full ${r === 1 ? 'bg-emerald-400' : 'bg-rose-500'}`} />
      ))}
    </div>
  )
}

// Ligne d'un joueur : nom, classement, forme, probabilité.
function PlayerRow({ player, isFavorite }) {
  return (
    <div className={`flex items-center justify-between rounded-xl px-3 py-2
      ${isFavorite ? 'surface-2' : ''}`}>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate font-semibold">{player.name}</span>
          {player.rank && (
            <span className="shrink-0 rounded-md surface-2 px-1.5 py-0.5 text-[10px]
              font-medium text-mid">#{player.rank}</span>
          )}
        </div>
        <div className="mt-1"><FormDots form={player.form_last5} /></div>
      </div>
      <span className={`ml-3 shrink-0 text-lg font-bold tabular-nums
        ${isFavorite ? 'text-brand' : 'text-mid'}`}>
        {Math.round(player.win_prob * 100)}%
      </span>
    </div>
  )
}

/**
 * Carte d'un match à venir : contexte (tournoi/tour/surface), les deux joueurs,
 * une barre de comparaison des probabilités et une jauge Recharts pour le favori.
 */
export default function MatchCard({ match }) {
  const { player1, player2 } = match
  const p1Fav = player1.win_prob >= player2.win_prob
  const favProb = Math.max(player1.win_prob, player2.win_prob) * 100
  const surfaceCls = SURFACE_STYLE[match.surface] ?? 'bg-slate-500/15 text-mid border-slate-500/30'

  return (
    <article className="glass p-4 transition-transform duration-200 hover:-translate-y-0.5">
      {/* En-tête contexte */}
      <header className="mb-3 flex items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md surface-2 px-2 py-0.5 text-xs font-medium">
            {match.tour}
          </span>
          <span className={`rounded-md border px-2 py-0.5 text-xs font-medium ${surfaceCls}`}>
            {match.surface}
          </span>
        </div>
        <span className="text-xs text-lo">{match.round}</span>
      </header>

      <div className="flex items-center gap-4">
        {/* Colonne joueurs + barre de comparaison */}
        <div className="flex-1 space-y-1">
          <PlayerRow player={player1} isFavorite={p1Fav} />
          <PlayerRow player={player2} isFavorite={!p1Fav} />

          {/* Barre horizontale : part de probabilité de chaque joueur. */}
          <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-slate-700/50">
            <div className="bg-gradient-to-r from-brand to-cyan-400"
                 style={{ width: `${player1.win_prob * 100}%` }} />
            <div className="bg-gradient-to-r from-fuchsia-500 to-brand-deep"
                 style={{ width: `${player2.win_prob * 100}%` }} />
          </div>
        </div>

        {/* Jauge Recharts du favori (masquée sur très petits écrans) */}
        <div className="hidden shrink-0 sm:block">
          <Gauge value={favProb} color={p1Fav ? '#22d3ee' : '#d946ef'} />
        </div>
      </div>

      <footer className="mt-3 text-xs text-lo">
        Favori : <span className="font-semibold text-hi">{match.favorite}</span>
        <span className="mx-1">·</span>{match.date}
      </footer>
    </article>
  )
}
