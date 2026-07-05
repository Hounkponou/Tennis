"""
Train the Grand Slam outcome model and save the artifacts the app needs.

Run:  python -m tennis_app.train

It builds the feature matrix by replaying every match chronologically, does a
time-based train/test evaluation (train on the past, test on the most recent
seasons), then refits on ALL data and saves:

    tennis_app/artifacts/model.joblib    - sklearn pipeline (impute+scale+logreg)
    tennis_app/artifacts/store.joblib    - PlayerFormStore holding current form
    tennis_app/artifacts/meta.joblib     - dropdown options + feature names

The model outputs P(player1 wins). Because features are diffs of pre-match
information only, the same pipeline is used unchanged to score live matchups.
"""

from __future__ import annotations

import random
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from tennis_app.features import FEATURES, PlayerFormStore, load_matches

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "grand_slams_all.csv"
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
TEST_FROM_YEAR = 2023          # matches from this year on are the held-out test set
SEED = 42


def build_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, PlayerFormStore]:
    """Replay matches in order, emitting one randomized feature row per match."""
    rng = random.Random(SEED)
    store = PlayerFormStore()
    rows = []

    for _, m in df.iterrows():
        # Randomly decide who is "player1" so the label is balanced 0/1.
        if rng.random() < 0.5:
            p1, p2, outcome = m["Winner"], m["Loser"], 1
            r1, r2, pt1, pt2 = m["WRank"], m["LRank"], m.get("WPts"), m.get("LPts")
        else:
            p1, p2, outcome = m["Loser"], m["Winner"], 0
            r1, r2, pt1, pt2 = m["LRank"], m["WRank"], m.get("LPts"), m.get("WPts")

        feats = store.features(
            p1, p2, m["Surface"], m["Tournament"], m["Round"],
            rank1=r1, rank2=r2, pts1=pt1, pts2=pt2,
        )
        feats["outcome"] = outcome
        feats["date"] = m["Date"]
        rows.append(feats)

        store.update(m)  # update AFTER building features (no leakage)

    return pd.DataFrame(rows), store


def bookmaker_baseline(df: pd.DataFrame) -> float | None:
    """Accuracy of 'lowest odds wins' on rows that have bookmaker odds."""
    odds = df.dropna(subset=["AvgW", "AvgL"]) if "AvgW" in df.columns else pd.DataFrame()
    odds = odds[(odds["AvgW"] > 0) & (odds["AvgL"] > 0)] if len(odds) else odds
    if odds.empty:
        return None
    correct = (odds["AvgW"] < odds["AvgL"]).mean()  # favourite (=winner) predicted
    return float(correct)


def main() -> None:
    print(f"Loading matches from {DATA} ...")
    df = load_matches(str(DATA))
    print(f"  {len(df)} matches, {df['Date'].min().date()} -> {df['Date'].max().date()}")

    print("Building feature matrix (chronological replay)...")
    matrix, store = build_matrix(df)

    X = matrix[FEATURES]
    y = matrix["outcome"].astype(int)
    is_test = matrix["date"].dt.year >= TEST_FROM_YEAR

    model = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(max_iter=10000)),
    ])

    # --- time-based evaluation ---
    model.fit(X[~is_test], y[~is_test])
    for label, mask in (("train", ~is_test), ("test", is_test)):
        pred = model.predict(X[mask])
        proba = model.predict_proba(X[mask])[:, 1]
        print(f"  {label:>5}: acc={accuracy_score(y[mask], pred):.4f}  "
              f"logloss={log_loss(y[mask], proba):.4f}  (n={mask.sum()})")

    base = bookmaker_baseline(df[df['Date'].dt.year >= TEST_FROM_YEAR])
    if base is not None:
        print(f"  bookmaker favourite baseline on test period: acc={base:.4f}")

    # --- refit on everything for serving ---
    print("Refitting final model on all data...")
    model.fit(X, y)

    ARTIFACTS.mkdir(exist_ok=True)
    meta = {
        "features": FEATURES,
        "players": sorted(store.players.keys()),
        "surfaces": sorted(df["Surface"].dropna().unique().tolist()),
        "tournaments": sorted(df["Tournament"].dropna().unique().tolist()),
        "rounds": ["1st Round", "2nd Round", "3rd Round", "4th Round",
                   "Quarterfinals", "Semifinals", "The Final"],
        "surface_of_tournament": (
            df.groupby("Tournament")["Surface"].agg(lambda s: s.mode().iloc[0]).to_dict()
        ),
        "trained_on": f"{df['Date'].min().date()} .. {df['Date'].max().date()}",
    }
    joblib.dump(model, ARTIFACTS / "model.joblib")
    joblib.dump(store, ARTIFACTS / "store.joblib")
    joblib.dump(meta, ARTIFACTS / "meta.joblib")
    print(f"Saved artifacts to {ARTIFACTS}")


if __name__ == "__main__":
    main()
