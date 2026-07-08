"""
ml/export_web.py — Export des artefacts pour le frontend statique.

Rôle : GitHub Actions (CRON) ─► python -m ml.export_web

Produit dans web/public/data/ :
    model.json    — modèle logistique "aplati" (features + prétraitement + poids)
                    pour rejouer l'inférence en JavaScript (onglet Simulation).
    players.json  — forme ACTUELLE de chaque joueur (taux pré-calculés).
    history.json  — résultats historiques des matchs (filtrables par tournoi,
                    année, surface, circuit, joueur).
    meta.json     — listes pour les filtres (tournois, surfaces, tours, années).

Grâce au choix d'une régression logistique, l'onglet Simulation calcule les
mêmes probabilités que le serveur, sans back-end.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.features import build_backtest_matrix, load_matches

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "models" / "model.joblib"
METRICS_PATH = ROOT / "models" / "metrics.json"
DATA = ROOT / "data" / "grand_slams_all.csv"
LIVE_RESULTS = ROOT / "data" / "live_results.csv"
OUT = ROOT / "web" / "public" / "data"

ROUND_ORDER = ["1st Round", "2nd Round", "3rd Round", "4th Round",
               "Quarterfinals", "Semifinals", "The Final"]
SURFACE_OF = {"Wimbledon": "Grass", "French Open": "Clay",
              "US Open": "Hard", "Australian Open": "Hard"}
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
#  1. Modèle logistique -> JSON exécutable en JS
# --------------------------------------------------------------------------- #
def export_model(bundle: dict) -> dict:
    """
    Aplati le pipeline LINÉAIRE (impute -> scale -> logreg) en coefficients
    bruts pour l'inférence JS. On prend `linear_model` (le meilleur modèle
    linéaire retenu), qui est identique à `model` si le meilleur global est
    lui-même linéaire.
    """
    pipe = bundle.get("linear_model", bundle["model"])
    imp = pipe.named_steps["impute"]
    scl = pipe.named_steps["scale"]
    clf = pipe.named_steps["clf"]

    model = {
        "version": bundle.get("version", "n/a"),
        "features": bundle["features"],
        # Inférence JS : x = valeur ou médiane si absente ;
        #                xs = (x - mean) / std ; z = Σ coef·xs + intercept ;
        #                p = 1 / (1 + e^-z)
        "impute_median": [round(float(v), 6) for v in imp.statistics_],
        "scale_mean": [round(float(v), 6) for v in scl.mean_],
        "scale_std": [round(float(v), 6) for v in scl.scale_],
        "coef": [round(float(v), 6) for v in clf.coef_[0]],
        "intercept": round(float(clf.intercept_[0]), 6),
    }
    return model


# --------------------------------------------------------------------------- #
#  2. Historique des matchs -> JSON filtrable
# --------------------------------------------------------------------------- #
def _score(row: pd.Series) -> str:
    """Reconstruit un score lisible depuis les colonnes de sets (W1/L1...)."""
    sets = []
    for i in range(1, 6):
        w, l = row.get(f"W{i}"), row.get(f"L{i}")
        if pd.notna(w) and pd.notna(l):
            try:  # les colonnes de sets sont parfois des flottants ("6.0")
                sets.append(f"{int(float(w))}-{int(float(l))}")
            except (ValueError, TypeError):
                continue
    return " ".join(sets)


def live_history_rows(store) -> list:
    """
    Convertit les résultats en direct (live_results.csv) au format historique,
    enrichis avec le circuit et le classement courant des joueurs (depuis le
    modèle). Ne garde que les matchs DÉJÀ JOUÉS (date <= aujourd'hui) pour rester
    cohérent. C'est ce qui évite que l'historique reste « bloqué en juin ».
    """
    if not LIVE_RESULTS.exists():
        return []
    live = pd.read_csv(LIVE_RESULTS)
    rows = []
    for _, r in live.iterrows():
        if str(r["date"]) > TODAY:
            continue
        w, l = r["winner"], r["loser"]
        wp, lp = store.players.get(w, {}), store.players.get(l, {})

        def _rank(p):
            v = p.get("rank")
            return int(v) if v is not None and v == v else None

        rows.append({
            "date": str(r["date"]), "year": int(str(r["date"])[:4]),
            "tour": wp.get("tour") or lp.get("tour"),
            "tournament": r["tournament"],
            "surface": SURFACE_OF.get(r["tournament"], ""),
            "round": "", "winner": w, "loser": l,
            "winner_rank": _rank(wp), "loser_rank": _rank(lp),
            "score": "",
        })
    return rows


def export_history(store) -> tuple[list, dict]:
    """Renvoie (liste de matchs, méta filtres) = historique tennis-data + résultats en direct."""
    df = pd.read_csv(DATA, low_memory=False)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Winner", "Loser", "Tournament", "Surface"])

    def rank(v):
        return int(v) if pd.notna(v) else None

    matches = []
    for _, r in df.iterrows():
        matches.append({
            "date": r["Date"].strftime("%Y-%m-%d"),
            "year": int(r["Date"].year),
            "tour": r.get("Tour"),
            "tournament": r["Tournament"],
            "surface": r["Surface"],
            "round": r["Round"],
            "winner": r["Winner"],
            "loser": r["Loser"],
            "winner_rank": rank(r.get("WRank")),
            "loser_rank": rank(r.get("LRank")),
            "score": _score(r),
        })

    # Fusion avec les résultats en direct (Wimbledon, etc.), dédupliquée.
    matches += live_history_rows(store)
    seen, deduped = set(), []
    for m in sorted(matches, key=lambda x: x["date"], reverse=True):  # plus récent d'abord
        key = (m["date"], m["winner"], m["loser"], m["tournament"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)

    tours = sorted({m["tour"] for m in deduped if m["tour"]})
    meta = {
        "tournaments": sorted({m["tournament"] for m in deduped}),
        "surfaces": sorted({m["surface"] for m in deduped if m["surface"]}),
        "tours": tours,
        "rounds": [r for r in ROUND_ORDER if any(m["round"] == r for m in deduped)],
        "years": sorted({m["year"] for m in deduped}, reverse=True),
    }
    return deduped, meta


# --------------------------------------------------------------------------- #
#  3. Backtest "Challenge" : le modèle avait-il raison, match après match ?
# --------------------------------------------------------------------------- #
def export_challenge(bundle: dict, holdout_accuracy) -> dict:
    """
    Rejoue tout l'historique et confronte la prédiction du modèle au résultat
    réel. Produit un taux de réussite global, des ventilations (année, surface,
    tournoi) et la liste des matchs récents avec le verdict (✓/✗).
    """
    df = load_matches(str(DATA))
    X, meta = build_backtest_matrix(df)
    proba = bundle["model"].predict_proba(X)[:, 1]  # P(le vrai vainqueur gagne)
    meta["prob_winner"] = proba.round(4)
    meta["correct"] = (proba >= 0.5)

    def agg(col):
        g = meta.groupby(col)["correct"].agg(["mean", "count"]).reset_index()
        return [{col: int(r[col]) if col == "year" else r[col],
                 "accuracy": round(float(r["mean"]), 4),
                 "n": int(r["count"])} for _, r in g.iterrows()]

    # --- Courbe de calibration (fiabilité) ---
    # Pour chaque match, le modèle donne p au vrai vainqueur (issue=1) et 1-p au
    # perdant (issue=0). On regroupe ces points par tranche de proba prédite et
    # on compare la proba MOYENNE prédite à la fréquence RÉELLE observée.
    preds = np.concatenate([proba, 1.0 - proba])
    obs = np.concatenate([np.ones_like(proba), np.zeros_like(proba)])
    edges = np.linspace(0, 1, 11)                       # 10 tranches
    idx = np.clip(np.digitize(preds, edges) - 1, 0, 9)
    calibration = []
    for b in range(10):
        m = idx == b
        if m.sum() == 0:
            continue
        calibration.append({
            "pred": round(float(preds[m].mean()), 4),   # proba moyenne prédite
            "obs": round(float(obs[m].mean()), 4),      # fréquence réelle
            "n": int(m.sum()),
        })

    recent = meta.sort_values("date", ascending=False).head(80)
    return {
        "calibration": calibration,
        "holdout_accuracy": holdout_accuracy,        # chiffre HONNÊTE (hors échantillon)
        "backtest_accuracy": round(float(meta["correct"].mean()), 4),
        "n_matches": int(len(meta)),
        "by_year": sorted(agg("year"), key=lambda r: r["year"]),
        "by_surface": agg("surface"),
        "by_tournament": agg("tournament"),
        "recent": [{
            "date": r["date"], "tour": r["tour"], "tournament": r["tournament"],
            "round": r["round"], "surface": r["surface"],
            "winner": r["winner"], "loser": r["loser"],
            "prob_winner": float(r["prob_winner"]), "correct": bool(r["correct"]),
        } for _, r in recent.iterrows()],
    }


# --------------------------------------------------------------------------- #
#  4. Orchestration
# --------------------------------------------------------------------------- #
def main() -> None:
    if not MODEL_PATH.exists():
        raise FileNotFoundError("models/model.joblib introuvable : lance ml.retrain")
    bundle = joblib.load(MODEL_PATH)

    OUT.mkdir(parents=True, exist_ok=True)

    # 1. Modèle JS.
    (OUT / "model.json").write_text(json.dumps(export_model(bundle), indent=2))

    # 2. Forme des joueurs.
    players = bundle["store"].browser_export()
    (OUT / "players.json").write_text(json.dumps(players, ensure_ascii=False))

    # 3. Historique (tennis-data + résultats en direct) + méta filtres.
    matches, meta = export_history(bundle["store"])
    (OUT / "history.json").write_text(json.dumps(matches, ensure_ascii=False))
    meta["n_players"] = len(players)
    meta["n_matches"] = len(matches)
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    # 4. Challenge (backtest). On récupère la précision honnête (hors échantillon)
    #    depuis metrics.json comme chiffre de référence.
    prev = json.loads(METRICS_PATH.read_text()) if METRICS_PATH.exists() else {}
    holdout_acc = prev.get("metrics", {}).get("accuracy")
    challenge = export_challenge(bundle, holdout_acc)
    (OUT / "challenge.json").write_text(json.dumps(challenge, ensure_ascii=False))

    print(f"[export_web] model.json | players.json ({len(players)} joueurs) | "
          f"history.json ({len(matches)} matchs) | meta.json | "
          f"challenge.json (backtest {challenge['backtest_accuracy']})")


if __name__ == "__main__":
    main()
