// Moteur d'inférence côté navigateur (onglet Simulation).
//
// Rejoue EXACTEMENT le pipeline sklearn (impute -> standardise -> logistique)
// à partir de model.json + players.json. Vérifié : identique au serveur à ~1e-6.

import { loadJSON } from './data.js'

let _model = null
let _players = null

// Charge (une fois) le modèle aplati + la forme des joueurs.
export async function loadSim() {
  if (!_model) {
    const [model, players] = await Promise.all([
      loadJSON('model.json'),
      loadJSON('players.json'),
    ])
    _model = model
    _players = players
  }
  return { model: _model, players: _players }
}

const sub = (x, y) => (x == null || y == null ? null : x - y)
const cat = (dict, key) => (dict && key in dict ? dict[key] : null)

// Reconstruit le vecteur de features (différences joueur1 - joueur2).
export function computeFeatures(players, n1, n2, ctx) {
  const a = players[n1]
  const b = players[n2]
  return {
    diff_rank: a.rank == null || b.rank == null ? null : a.rank - b.rank,
    diff_pts: a.pts == null || b.pts == null ? null : a.pts - b.pts,
    diff_experience: Math.log1p(a.matches) - Math.log1p(b.matches),
    diff_global_win_rate: sub(a.wr_global, b.wr_global),
    diff_win_rate_last5: sub(a.wr5, b.wr5),
    diff_win_rate_last10: sub(a.wr10, b.wr10),
    diff_win_rate_last20: sub(a.wr20, b.wr20),
    diff_surface_win_rate: sub(cat(a.wr_surface, ctx.surface), cat(b.wr_surface, ctx.surface)),
    diff_tourney_win_rate: sub(cat(a.wr_tourney, ctx.tournament), cat(b.wr_tourney, ctx.tournament)),
    diff_round_win_rate: sub(cat(a.wr_round, ctx.round), cat(b.wr_round, ctx.round)),
  }
}

// Probabilité que le joueur1 gagne (identique à model.predict_proba[:,1]).
export function predictProb(model, players, n1, n2, ctx) {
  const f = computeFeatures(players, n1, n2, ctx)
  let z = model.intercept
  model.features.forEach((name, i) => {
    let x = f[name]
    if (x == null || Number.isNaN(x)) x = model.impute_median[i]  // imputation médiane
    const xs = (x - model.scale_mean[i]) / model.scale_std[i]     // standardisation
    z += model.coef[i] * xs
  })
  return 1 / (1 + Math.exp(-z))  // sigmoïde
}
