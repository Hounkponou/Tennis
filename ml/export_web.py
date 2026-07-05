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
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.features import build_backtest_matrix, load_matches

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "models" / "model.joblib"
METRICS_PATH = ROOT / "models" / "metrics.json"
DATA = ROOT / "data" / "grand_slams_all.csv"
OUT = ROOT / "web" / "public" / "data"

ROUND_ORDER = ["1st Round", "2nd Round", "3rd Round", "4th Round",
               "Quarterfinals", "Semifinals", "The Final"]


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


def export_history() -> tuple[list, dict]:
    """Charge le CSV complet et renvoie (liste de matchs, méta pour filtres)."""
    df = pd.read_csv(DATA, low_memory=False)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Winner", "Loser", "Tournament", "Surface"])
    df = df.sort_values("Date", ascending=False)  # plus récent d'abord

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

    meta = {
        "tournaments": sorted(df["Tournament"].dropna().unique().tolist()),
        "surfaces": sorted(df["Surface"].dropna().unique().tolist()),
        "tours": sorted(df["Tour"].dropna().unique().tolist()),
        "rounds": [r for r in ROUND_ORDER if r in set(df["Round"])],
        "years": sorted(df["Date"].dt.year.unique().tolist(), reverse=True),
    }
    return matches, meta


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

    recent = meta.sort_values("date", ascending=False).head(80)
    return {
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

    # 3. Historique + méta filtres.
    matches, meta = export_history()
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
