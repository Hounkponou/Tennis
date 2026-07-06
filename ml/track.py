"""
ml/track.py — Registre de suivi des prédictions (résultat prédit vs réel).

Rôle : GitHub Actions (CRON) ─► python -m ml.track   (après ml.predict)

Idée : on garde une trace PERSISTANTE de chaque prédiction publiée, puis on la
« résout » quand le match a été joué (le résultat arrive dans l'historique
grâce au scraper). On en tire un taux de réussite = prédictions correctes /
prédictions résolues.

Cycle de vie d'une entrée :
    pending  (match à venir, on connaît la prédiction, pas encore le résultat)
       │  … le match est joué, son résultat entre dans grand_slams_all.csv …
       ▼
    resolved (on compare le vainqueur prédit au vainqueur réel -> correct ?)

Amorçage : au tout premier run, le registre est vide et les matchs à venir ne
sont pas encore joués -> la page serait vide. On l'amorce donc avec les
derniers matchs réels de l'historique (prédiction pré-match du modèle vs
résultat connu), pour que le suivi soit immédiatement parlant.

Sortie committée : web/public/data/tracking.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib

from ml.features import build_backtest_matrix, load_matches

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "grand_slams_all.csv"
MODEL_PATH = ROOT / "models" / "model.joblib"
PRED_PATH = ROOT / "web" / "public" / "data" / "predictions.json"
LEDGER = ROOT / "web" / "public" / "data" / "tracking.json"

BOOTSTRAP_K = 60   # nb de matchs récents pour amorcer le registre


def _pair(a: str, b: str) -> tuple:
    """Clé de match insensible à l'ordre des joueurs."""
    return tuple(sorted([a, b]))


def history_index(df) -> dict:
    """Index {(paire de joueurs, tournoi) -> vainqueur réel} depuis l'historique."""
    idx = {}
    for _, r in df.iterrows():
        idx[(_pair(r["Winner"], r["Loser"]), r["Tournament"])] = r["Winner"]
    return idx


def bootstrap(entries: dict, df) -> None:
    """Amorce le registre avec les derniers matchs réels (prédiction vs résultat)."""
    X, meta = build_backtest_matrix(df)
    proba = joblib.load(MODEL_PATH)["model"].predict_proba(X)[:, 1]
    meta = meta.copy()
    meta["p"] = proba
    for _, r in meta.tail(BOOTSTRAP_K).iterrows():
        p = float(r["p"])                                   # P(le vrai vainqueur gagne)
        favorite = r["winner"] if p >= 0.5 else r["loser"]  # ce que le modèle prédisait
        eid = f"seed-{r['date']}-{r['winner']}-{r['loser']}"
        entries[eid] = {
            "id": eid, "origin": "historique",
            "date": r["date"], "tournament": r["tournament"],
            "player1": r["winner"], "player2": r["loser"],
            "predicted_winner": favorite,
            "predicted_prob": round(max(p, 1 - p), 4),
            "actual_winner": r["winner"],
            "correct": bool(p >= 0.5),
            "status": "resolved",
        }


def add_live_predictions(entries: dict) -> None:
    """Ajoute les prédictions des matchs à venir (statut 'pending')."""
    if not PRED_PATH.exists():
        return
    preds = json.loads(PRED_PATH.read_text())
    for m in preds.get("matches", []):
        eid = f"live-{m['id']}"
        if eid in entries:
            continue  # déjà suivie
        p1, p2 = m["player1"], m["player2"]
        entries[eid] = {
            "id": eid, "origin": "à venir",
            "date": m["date"], "tournament": m["tournament"],
            "player1": p1["name"], "player2": p2["name"],
            "predicted_winner": m["favorite"],
            "predicted_prob": round(max(p1["win_prob"], p2["win_prob"]), 4),
            "actual_winner": None, "correct": None, "status": "pending",
        }


def resolve_pending(entries: dict, idx: dict) -> None:
    """Résout les entrées en attente dont le match figure désormais à l'historique."""
    for e in entries.values():
        if e["status"] != "pending":
            continue
        winner = idx.get((_pair(e["player1"], e["player2"]), e["tournament"]))
        if winner:
            e["actual_winner"] = winner
            e["correct"] = (e["predicted_winner"] == winner)
            e["status"] = "resolved"


def main() -> None:
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {"entries": []}
    entries = {e["id"]: e for e in ledger["entries"]}

    df = load_matches(str(DATA))
    idx = history_index(df)

    if not any(e["status"] == "resolved" for e in entries.values()):
        bootstrap(entries, df)          # premier run : on amorce
    add_live_predictions(entries)       # nouvelles prédictions à suivre
    resolve_pending(entries, idx)       # on résout ce qui a été joué depuis

    resolved = [e for e in entries.values() if e["status"] == "resolved"]
    correct = sum(1 for e in resolved if e["correct"])
    pending = [e for e in entries.values() if e["status"] == "pending"]

    # Ordre d'affichage : matchs à venir d'abord, puis résolus du plus récent.
    ordered = (sorted(pending, key=lambda e: e["date"])
               + sorted(resolved, key=lambda e: e["date"], reverse=True))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "success_rate": round(correct / len(resolved), 4) if resolved else None,
        "n_correct": correct,
        "n_resolved": len(resolved),
        "n_pending": len(pending),
        "entries": ordered,
    }
    LEDGER.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    rate = f"{payload['success_rate']*100:.1f}%" if payload["success_rate"] is not None else "—"
    print(f"[track] {len(resolved)} résolues ({correct} ✓, taux {rate}), "
          f"{len(pending)} en attente -> {LEDGER.name}")


if __name__ == "__main__":
    main()
