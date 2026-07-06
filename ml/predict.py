"""
ml/predict.py — Inférence sur les matchs à venir (100 % fichiers).

Rôle : GitHub Actions (CRON) ─► python -m ml.predict

Charge le bundle entraîné (models/model.joblib = modèle + form store + features),
lit data/upcoming.csv, calcule pour chaque match la probabilité de victoire de
chaque joueur à partir de leur FORME ACTUELLE (état final du form store), puis
écrit web/public/data/predictions.json que le frontend React consomme.

Sortie committée par le workflow : web/public/data/predictions.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "models" / "model.joblib"
METRICS_PATH = ROOT / "models" / "metrics.json"
UPCOMING = ROOT / "data" / "upcoming.csv"
OUT = ROOT / "web" / "public" / "data" / "predictions.json"


def load_bundle() -> dict:
    if not MODEL_PATH.exists():
        raise FileNotFoundError("models/model.joblib introuvable : lance d'abord ml.retrain")
    return joblib.load(MODEL_PATH)


def player_block(store, name: str, prob: float) -> dict:
    """Bloc joueur pour le JSON (nom, classement, forme récente, probabilité)."""
    s = store.summary(name)
    return {
        "name": name,
        "rank": s["rank"],
        "form_last5": s["form_last5"],   # ex: [1,1,0,1,1]
        "matches_played": s["matches"],
        "win_prob": round(prob, 4),
    }


def main() -> None:
    bundle = load_bundle()
    model, store, features = bundle["model"], bundle["store"], bundle["features"]
    version = bundle.get("version", "n/a")

    if not UPCOMING.exists():
        print("[predict] data/upcoming.csv absent : rien à prédire.")
        return
    upcoming = pd.read_csv(UPCOMING)
    if upcoming.empty:
        print("[predict] aucun match à venir dans upcoming.csv.")

    matches = []
    skipped = []
    for _, row in upcoming.iterrows():
        p1, p2 = str(row["player1"]).strip(), str(row["player2"]).strip()

        # On ne prédit que si les DEUX joueurs sont connus du modèle (ont un
        # historique) ; sinon la prédiction n'aurait pas de sens.
        if p1 not in store.players or p2 not in store.players:
            skipped.append(f"{p1} vs {p2}")
            continue

        # Le round peut être absent (calendrier scrapé) -> chaîne vide, que le
        # modèle traitera par imputation.
        rnd = str(row["round"]) if pd.notna(row["round"]) else ""

        feats = store.features(p1, p2, row["surface"], row["tournament"], rnd)
        X = pd.DataFrame([[feats[f] for f in features]], columns=features)
        prob1 = float(model.predict_proba(X)[0, 1])

        matches.append({
            "id": str(row.get("id", f"{p1}-{p2}")),
            "date": str(row["date"]),
            "tour": store.summary(p1)["tour"],   # ATP / WTA (pour les filtres)
            "tournament": row["tournament"],
            "surface": row["surface"],
            "round": rnd,
            "player1": player_block(store, p1, prob1),
            "player2": player_block(store, p2, 1.0 - prob1),
            "favorite": p1 if prob1 >= 0.5 else p2,
        })

    metrics = json.loads(METRICS_PATH.read_text()) if METRICS_PATH.exists() else {}
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": version,
        "model_metrics": metrics.get("metrics", {}),
        "count": len(matches),
        "matches": matches,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"[predict] {len(matches)} prédictions écrites -> {OUT.relative_to(ROOT)}")
    if skipped:
        print(f"[predict] {len(skipped)} match(s) ignoré(s) (joueur inconnu) : "
              + ", ".join(skipped[:5]) + ("..." if len(skipped) > 5 else ""))


if __name__ == "__main__":
    main()
