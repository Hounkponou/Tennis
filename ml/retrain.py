"""
ml/retrain.py — Réentraînement continu + sélection du meilleur modèle (MLOps).

Rôle : GitHub Actions (CRON quotidien) ─► python -m ml.retrain

Logique :
    1. DÉCLENCHEUR ANTI-DÉRIVE : réentraîne seulement si assez de nouveaux
       matchs sont apparus (watermark dans models/metrics.json), sauf --force.
    2. FEATURES : replay chronologique via ml.features (train == serve).
    3. SPLIT TEMPOREL : train = passé, test = fin de période.
    4. COMPÉTITION DE MODÈLES : à CHAQUE run, plusieurs modèles s'affrontent
       (régression logistique vs gradient boosting), chacun optimisé par
       GridSearchCV + TimeSeriesSplit. On retient :
         - best_model  : le meilleur au global (sert aux prédictions "à venir"
                         et au Challenge) ;
         - best_linear : le meilleur modèle LINÉAIRE (exporté en JSON pour la
                         simulation navigateur, qui ne peut pas exécuter un
                         modèle à base d'arbres).
       Si le meilleur global est déjà linéaire, les deux sont identiques.
    5. RÉ-AJUSTEMENT des deux modèles retenus sur toutes les données.
    6. SAUVEGARDE : bundle joblib (best_model + best_linear + form store +
       features) dans models/model.joblib ; classement complet + métriques
       dans models/metrics.json.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.features import FEATURES, build_training_matrix, load_matches

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "grand_slams_all.csv"
MODELS = ROOT / "models"
MODEL_PATH = MODELS / "model.joblib"
METRICS_PATH = MODELS / "metrics.json"

TEST_FRACTION = 0.15
CV_SPLITS = 4
MIN_NEW_MATCHES = int(os.environ.get("MIN_NEW_MATCHES", 50))


# --------------------------------------------------------------------------- #
#  1. Déclencheur anti-dérive
# --------------------------------------------------------------------------- #
def load_previous_metrics() -> dict | None:
    if METRICS_PATH.exists():
        return json.loads(METRICS_PATH.read_text())
    return None


def should_retrain(n_matches: int, force: bool) -> tuple[bool, str]:
    prev = load_previous_metrics()
    if force:
        return True, "forcé (--force)"
    if prev is None or not MODEL_PATH.exists():
        return True, "aucun modèle existant (premier entraînement)"
    seen = prev.get("n_matches_trained_on", 0)
    n_new = n_matches - seen
    if n_new >= MIN_NEW_MATCHES:
        return True, f"{n_new} nouveaux matchs (seuil {MIN_NEW_MATCHES})"
    return False, f"seulement {n_new} nouveaux matchs (< {MIN_NEW_MATCHES})"


# --------------------------------------------------------------------------- #
#  2. Candidats en compétition
# --------------------------------------------------------------------------- #
def build_candidates() -> list[dict]:
    """
    Renvoie la liste des modèles candidats. `linear=True` => exportable en JS.

    - Régression logistique : linéaire, interprétable, exportable navigateur.
    - HistGradientBoosting  : non linéaire, souvent plus puissant sur données
      tabulaires, gère nativement les valeurs manquantes.
    """
    logreg = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),          # nécessaire pour un modèle linéaire
        ("clf", LogisticRegression(max_iter=10000)),
    ])
    hgb = Pipeline([
        ("impute", SimpleImputer(strategy="median")),   # inoffensif pour HGB
        ("clf", HistGradientBoostingClassifier(random_state=42)),
    ])
    return [
        {"name": "LogisticRegression", "pipe": logreg, "linear": True,
         "grid": {"clf__C": [0.3, 1.0, 3.0]}},
        {"name": "HistGradientBoosting", "pipe": hgb, "linear": False,
         "grid": {"clf__max_depth": [None, 6], "clf__learning_rate": [0.05, 0.1]}},
    ]


def _eval(est, X_te, y_te) -> dict:
    proba = est.predict_proba(X_te)[:, 1]
    pred = (proba >= 0.5).astype(int)
    return {
        "accuracy": round(float(accuracy_score(y_te, pred)), 4),
        "log_loss": round(float(log_loss(y_te, proba)), 4),
        "roc_auc": round(float(roc_auc_score(y_te, proba)), 4),
    }


def select_best(X: pd.DataFrame, y: pd.Series) -> dict:
    """
    Fait concourir tous les candidats (GridSearch + CV temporelle sur le train,
    évaluation sur le test held-out) et renvoie le classement + les gagnants.
    """
    cut = int(len(X) * (1 - TEST_FRACTION))
    X_tr, X_te = X.iloc[:cut], X.iloc[cut:]
    y_tr, y_te = y.iloc[:cut], y.iloc[cut:]
    cv = TimeSeriesSplit(n_splits=CV_SPLITS)

    results = []
    for cand in build_candidates():
        search = GridSearchCV(cand["pipe"], cand["grid"], scoring="neg_log_loss",
                              cv=cv, n_jobs=-1, refit=True)
        search.fit(X_tr, y_tr)
        metrics = _eval(search.best_estimator_, X_te, y_te)
        results.append({
            "name": cand["name"],
            "linear": cand["linear"],
            "estimator": search.best_estimator_,
            "params": search.best_params_,
            "metrics": metrics,
        })
        print(f"  - {cand['name']:>22} : acc={metrics['accuracy']} "
              f"logloss={metrics['log_loss']} auc={metrics['roc_auc']}")

    # On choisit par log-loss (qualité des probabilités affichées).
    best = min(results, key=lambda r: r["metrics"]["log_loss"])
    linear = min((r for r in results if r["linear"]),
                 key=lambda r: r["metrics"]["log_loss"])
    print(f"  => meilleur global : {best['name']} | "
          f"meilleur linéaire (simulation) : {linear['name']}")
    return {"results": results, "best": best, "linear": linear}


# --------------------------------------------------------------------------- #
#  3. Détection de dérive
# --------------------------------------------------------------------------- #
def detect_drift(prev: dict | None, new_metrics: dict) -> str | None:
    if not prev:
        return None
    old = prev.get("metrics", {}).get("accuracy")
    if old is None:
        return None
    delta = new_metrics["accuracy"] - old
    if delta < -0.02:
        return (f"⚠️ Dérive possible : accuracy {new_metrics['accuracy']:.3f} "
                f"< précédent {old:.3f} (Δ={delta:+.3f}).")
    return None


# --------------------------------------------------------------------------- #
#  4. Orchestration
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="Réentraînement continu")
    parser.add_argument("--force", action="store_true",
                        help="réentraîner même sans nouveaux matchs")
    args = parser.parse_args()

    df = load_matches(str(DATA))
    n_matches = len(df)

    go, reason = should_retrain(n_matches, args.force)
    print(f"[retrain] décision : {'OUI' if go else 'NON'} — {reason}")
    if not go:
        return

    print(f"[retrain] {n_matches} matchs "
          f"({df['Date'].min().date()} -> {df['Date'].max().date()})")
    X, y, dates, store = build_training_matrix(df)

    print("[retrain] compétition de modèles (GridSearch + CV temporelle) :")
    sel = select_best(X, y)
    best, linear = sel["best"], sel["linear"]

    alert = detect_drift(load_previous_metrics(), best["metrics"])
    if alert:
        print(f"[retrain] {alert}")

    # 5. Ré-ajustement des modèles retenus sur TOUTES les données.
    print("[retrain] ré-ajustement final sur toutes les données...")
    best_model = clone(best["estimator"]).fit(X, y)
    linear_model = (best_model if linear["name"] == best["name"]
                    else clone(linear["estimator"]).fit(X, y))

    # 6. Sauvegarde.
    MODELS.mkdir(exist_ok=True)
    version = datetime.now(timezone.utc).strftime("%Y.%m.%d-%H%M")
    joblib.dump({
        "model": best_model,          # meilleur global (prédictions + challenge)
        "linear_model": linear_model,  # meilleur linéaire (export navigateur)
        "store": store,
        "features": FEATURES,
        "version": version,
    }, MODEL_PATH)

    METRICS_PATH.write_text(json.dumps({
        "version": version,
        "chosen_model": best["name"],
        "chosen_linear_model": linear["name"],
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "trained_through": str(df["Date"].max().date()),
        "n_matches_trained_on": n_matches,
        "hyperparams": best["params"],
        "metrics": best["metrics"],
        "leaderboard": [
            {"name": r["name"], "linear": r["linear"], **r["metrics"]}
            for r in sel["results"]
        ],
    }, indent=2))
    print(f"[retrain] ✅ modèle {version} ({best['name']}) sauvegardé.")


if __name__ == "__main__":
    main()
