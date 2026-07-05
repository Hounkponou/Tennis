"""
Feature engineering for Grand Slam match prediction.

This module is the single source of truth for how a match is turned into a
feature vector. It is used both at TRAINING time (to build the dataset) and at
SERVING time (the Streamlit app), so the two can never drift apart.

Core idea (same as the original notebook, adapted to the tennis-data.co.uk
columns): we keep a running "form" state for every player and, for each match,
we build features from the state *as it was before the match* (no leakage),
then update the state with the match result. After processing every historical
match in chronological order, each player's state holds their CURRENT form,
which is exactly what we need to predict a brand-new match.

All features are differences  player1 - player2, so the model does not learn a
"player1 is usually the winner" bias.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import pandas as pd

# Ordered list of feature columns. Order matters: train and serve must agree.
FEATURES = [
    "diff_rank",            # ATP/WTA ranking (lower is better)
    "diff_pts",             # ranking points
    "diff_experience",      # log difference of number of matches played
    "diff_global_win_rate",
    "diff_win_rate_last5",
    "diff_win_rate_last10",
    "diff_win_rate_last20",
    "diff_surface_win_rate",
    "diff_tourney_win_rate",
    "diff_round_win_rate",
    "diff_h2h",             # head-to-head win rate of p1 against p2 (minus 0.5)
]

WINDOWS = (5, 10, 20)


# --------------------------------------------------------------------------- #
# Data loading / cleaning
# --------------------------------------------------------------------------- #
def load_matches(csv_path: str) -> pd.DataFrame:
    """Load the combined Grand Slam CSV and return clean, chronological matches."""
    df = pd.read_csv(csv_path, low_memory=False)

    keep = [
        "Date", "Tour", "Tournament", "Surface", "Round", "Best of",
        "Winner", "Loser", "WRank", "LRank", "WPts", "LPts",
        "AvgW", "AvgL",  # average bookmaker odds (used only as a baseline)
    ]
    df = df[[c for c in keep if c in df.columns]].copy()

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Winner", "Loser", "Surface", "Round"])

    # Ranks are needed as features; points are helpful but sometimes missing.
    for col in ("WRank", "LRank", "WPts", "LPts", "AvgW", "AvgL"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["WRank", "LRank"])

    df = df.sort_values("Date").reset_index(drop=True)
    return df


# --------------------------------------------------------------------------- #
# Player form store
# --------------------------------------------------------------------------- #
def _zero_pair() -> list:
    # Module-level factory (not a lambda) so the store stays picklable/joblib-safe.
    return [0, 0]


def _new_player() -> dict:
    return {
        "results": [],                    # 1/0 per past match, chronological
        "surface": defaultdict(_zero_pair),   # surface -> [wins, played]
        "tourney": defaultdict(_zero_pair),   # tournament -> [wins, played]
        "round": defaultdict(_zero_pair),     # round -> [wins, played]
        "h2h": defaultdict(_zero_pair),       # opponent -> [wins, played]
        "rank": np.nan,                   # most recent known ranking
        "pts": np.nan,                    # most recent known points
        "last_date": None,
        "tour": None,
    }


class PlayerFormStore:
    """Holds the running form of every player and builds feature vectors."""

    def __init__(self) -> None:
        self.players: dict[str, dict] = {}

    # -- internal helpers ---------------------------------------------------- #
    def _get(self, name: str) -> dict:
        if name not in self.players:
            self.players[name] = _new_player()
        return self.players[name]

    @staticmethod
    def _rate(pair) -> float:
        wins, played = pair
        return wins / played if played > 0 else np.nan

    @staticmethod
    def _last_k_rate(results: list, k: int) -> float:
        window = results[-k:]
        return float(np.mean(window)) if window else np.nan

    # -- feature building (read-only, pre-match) ----------------------------- #
    def features(
        self,
        p1: str,
        p2: str,
        surface: str,
        tourney: str,
        rnd: str,
        rank1: float | None = None,
        rank2: float | None = None,
        pts1: float | None = None,
        pts2: float | None = None,
    ) -> dict:
        """Build the diff feature dict for a hypothetical p1-vs-p2 match."""
        a, b = self._get(p1), self._get(p2)

        r1 = a["rank"] if rank1 is None else rank1
        r2 = b["rank"] if rank2 is None else rank2
        pt1 = a["pts"] if pts1 is None else pts1
        pt2 = b["pts"] if pts2 is None else pts2

        exp1 = math.log1p(len(a["results"]))
        exp2 = math.log1p(len(b["results"]))

        h2h1 = self._rate(a["h2h"][p2])   # p1's win rate vs p2
        h2h = (h2h1 - 0.5) if not np.isnan(h2h1) else np.nan

        return {
            "diff_rank": r1 - r2,
            "diff_pts": pt1 - pt2,
            "diff_experience": exp1 - exp2,
            "diff_global_win_rate": self._last_k_rate(a["results"], 10**9)
            - self._last_k_rate(b["results"], 10**9),
            "diff_win_rate_last5": self._last_k_rate(a["results"], 5)
            - self._last_k_rate(b["results"], 5),
            "diff_win_rate_last10": self._last_k_rate(a["results"], 10)
            - self._last_k_rate(b["results"], 10),
            "diff_win_rate_last20": self._last_k_rate(a["results"], 20)
            - self._last_k_rate(b["results"], 20),
            "diff_surface_win_rate": self._rate(a["surface"][surface])
            - self._rate(b["surface"][surface]),
            "diff_tourney_win_rate": self._rate(a["tourney"][tourney])
            - self._rate(b["tourney"][tourney]),
            "diff_round_win_rate": self._rate(a["round"][rnd])
            - self._rate(b["round"][rnd]),
            "diff_h2h": h2h,
        }

    # -- state update (post-match) ------------------------------------------- #
    def update(self, row: pd.Series) -> None:
        """Update winner and loser state with the outcome of a real match."""
        w, l = row["Winner"], row["Loser"]
        surface, tourney, rnd = row["Surface"], row["Tournament"], row["Round"]

        win, los = self._get(w), self._get(l)

        win["results"].append(1)
        los["results"].append(0)

        win["surface"][surface][0] += 1
        win["surface"][surface][1] += 1
        los["surface"][surface][1] += 1

        win["tourney"][tourney][0] += 1
        win["tourney"][tourney][1] += 1
        los["tourney"][tourney][1] += 1

        win["round"][rnd][0] += 1
        win["round"][rnd][1] += 1
        los["round"][rnd][1] += 1

        win["h2h"][l][0] += 1
        win["h2h"][l][1] += 1
        los["h2h"][w][1] += 1

        # Latest known ranking / points / tour for serving.
        win.update(rank=row["WRank"], pts=row.get("WPts", np.nan),
                   last_date=row["Date"], tour=row["Tour"])
        los.update(rank=row["LRank"], pts=row.get("LPts", np.nan),
                   last_date=row["Date"], tour=row["Tour"])

    # -- convenience for the UI --------------------------------------------- #
    def summary(self, name: str) -> dict:
        """Current-form snapshot for display in the app."""
        p = self._get(name)
        results = p["results"]
        return {
            "matches": len(results),
            "win_rate": self._last_k_rate(results, 10**9),
            "form_last10": results[-10:],
            "rank": p["rank"],
            "pts": p["pts"],
            "tour": p["tour"],
            "last_date": p["last_date"],
        }
