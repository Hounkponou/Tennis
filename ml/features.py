"""
ml/features.py — Ingénierie des features (partagée entraînement / inférence).

RÈGLE MLOps : train == serve. Le MÊME code fabrique les features à
l'entraînement (retrain.py) ET à l'inférence (predict.py), ce qui élimine le
"train/serve skew".

Version 100 % fichiers (sans base de données) : on lit le CSV historique
`data/grand_slams_all.csv`. Les joueurs sont identifiés par leur nom (colonnes
Winner/Loser de tennis-data.co.uk).

Principe métier : on maintient un "état de forme" par joueur. Pour chaque match
on calcule les features à partir de l'état AVANT le match (aucune fuite), puis
on met à jour l'état. Après avoir rejoué tout l'historique dans l'ordre
chronologique, l'état de chaque joueur = sa FORME ACTUELLE : exactement ce
qu'il faut pour prédire un match à venir.

Toutes les features sont des différences joueur1 - joueur2 (pas de biais
"joueur1 gagne plus souvent").
"""

from __future__ import annotations

import math
import random
from collections import defaultdict

import numpy as np
import pandas as pd

# --- Ordre canonique des features. train et serve DOIVENT utiliser cet ordre.
FEATURES = [
    "diff_rank",              # classement (plus petit = meilleur)
    "diff_pts",               # points ATP/WTA
    "diff_experience",        # log(nb matchs joués) différentiel
    "diff_global_win_rate",   # taux de victoire global
    "diff_win_rate_last5",    # forme récente (5 derniers)
    "diff_win_rate_last10",   # forme récente (10 derniers)
    "diff_win_rate_last20",   # forme récente (20 derniers)
    "diff_surface_win_rate",  # taux de victoire sur la surface du match
    "diff_tourney_win_rate",  # taux de victoire sur ce tournoi
    "diff_round_win_rate",    # taux de victoire à ce tour
]
# NB : on n'inclut PAS le head-to-head. Raison : la simulation tourne côté
# navigateur (site statique) et doit produire EXACTEMENT les mêmes chiffres que
# le serveur. Un h2h nécessiterait d'exporter toute la matrice des
# confrontations ; on le retire pour garder train == serve == navigateur.

SEED = 42


# --------------------------------------------------------------------------- #
#  Chargement / nettoyage de l'historique
# --------------------------------------------------------------------------- #
def load_matches(csv_path: str) -> pd.DataFrame:
    """Charge le CSV historique et renvoie des matchs propres et chronologiques."""
    df = pd.read_csv(csv_path, low_memory=False)

    keep = [
        "Date", "Tour", "Tournament", "Surface", "Round", "Best of",
        "Winner", "Loser", "WRank", "LRank", "WPts", "LPts", "AvgW", "AvgL",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Winner", "Loser", "Surface", "Round"])
    for col in ("WRank", "LRank", "WPts", "LPts", "AvgW", "AvgL"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["WRank", "LRank"])
    return df.sort_values("Date").reset_index(drop=True)


# --------------------------------------------------------------------------- #
#  État de forme par joueur
# --------------------------------------------------------------------------- #
def _zero_pair() -> list:
    # Factory de module (pas une lambda) -> état sérialisable par joblib.
    return [0, 0]


def _new_player() -> dict:
    return {
        "results": [],                        # 1/0 par match passé (chronologique)
        "surface": defaultdict(_zero_pair),   # surface -> [victoires, joués]
        "tourney": defaultdict(_zero_pair),   # tournoi  -> [victoires, joués]
        "round": defaultdict(_zero_pair),     # tour     -> [victoires, joués]
        "rank": np.nan,                       # dernier classement connu
        "pts": np.nan,                        # derniers points connus
        "tour": None,
        "last_date": None,
    }


class PlayerFormStore:
    """Maintient la forme courante de chaque joueur et fabrique les features."""

    def __init__(self) -> None:
        self.players: dict[str, dict] = {}   # clé = nom du joueur

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

    def features(self, p1: str, p2: str, surface: str, tourney: str, rnd: str,
                 rank1=None, rank2=None, pts1=None, pts2=None) -> dict:
        """Vecteur de features (diffs) pour un match hypothétique p1 vs p2."""
        a, b = self._get(p1), self._get(p2)
        r1 = a["rank"] if rank1 is None else rank1
        r2 = b["rank"] if rank2 is None else rank2
        pt1 = a["pts"] if pts1 is None else pts1
        pt2 = b["pts"] if pts2 is None else pts2

        exp1 = math.log1p(len(a["results"]))
        exp2 = math.log1p(len(b["results"]))

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
        }

    def update(self, row: pd.Series) -> None:
        """Met à jour l'état du gagnant et du perdant après un match réel."""
        w, l = row["Winner"], row["Loser"]
        win, los = self._get(w), self._get(l)

        win["results"].append(1)
        los["results"].append(0)
        for key, col in (("surface", "Surface"), ("tourney", "Tournament"),
                         ("round", "Round")):
            val = row[col]
            win[key][val][0] += 1
            win[key][val][1] += 1
            los[key][val][1] += 1

        win.update(rank=row["WRank"], pts=row.get("WPts", np.nan),
                   tour=row["Tour"], last_date=row["Date"])
        los.update(rank=row["LRank"], pts=row.get("LPts", np.nan),
                   tour=row["Tour"], last_date=row["Date"])

    def browser_export(self) -> dict:
        """
        Exporte la forme ACTUELLE de chaque joueur sous une forme directement
        consommable en JavaScript (taux pré-calculés). Permet à l'onglet
        Simulation de recalculer les features côté navigateur, à l'identique.
        """
        def rnd(v):  # None si NaN, sinon arrondi à 4 décimales
            return None if v != v else round(float(v), 4)

        def cat_rates(table: dict) -> dict:
            return {k: rnd(self._rate(v)) for k, v in table.items() if v[1] > 0}

        out = {}
        for name, p in self.players.items():
            r = p["results"]
            out[name] = {
                "tour": p["tour"],
                "rank": None if p["rank"] != p["rank"] else int(p["rank"]),
                "pts": None if p["pts"] != p["pts"] else int(p["pts"]),
                "matches": len(r),
                "last_year": p["last_date"].year if p["last_date"] is not None else None,
                "wr_global": rnd(self._last_k_rate(r, 10**9)),
                "wr5": rnd(self._last_k_rate(r, 5)),
                "wr10": rnd(self._last_k_rate(r, 10)),
                "wr20": rnd(self._last_k_rate(r, 20)),
                "wr_surface": cat_rates(p["surface"]),
                "wr_tourney": cat_rates(p["tourney"]),
                "wr_round": cat_rates(p["round"]),
            }
        return out

    def summary(self, name: str) -> dict:
        """Instantané de forme pour l'affichage (frontend / API)."""
        p = self._get(name)
        r = p["results"]
        return {
            "matches": len(r),
            "win_rate": self._last_k_rate(r, 10**9),
            "form_last5": r[-5:],
            "rank": None if p["rank"] != p["rank"] else int(p["rank"]),
            "tour": p["tour"],
        }


# --------------------------------------------------------------------------- #
#  Matrice d'entraînement (replay chronologique)
# --------------------------------------------------------------------------- #
def build_training_matrix(df: pd.DataFrame):
    """
    Rejoue les matchs et émet une ligne de features randomisée par match.
    Retourne (X, y, dates, store) ; `store` = forme ACTUELLE des joueurs.
    """
    rng = random.Random(SEED)
    store = PlayerFormStore()
    rows, labels, dates = [], [], []

    for _, m in df.iterrows():
        if rng.random() < 0.5:
            p1, p2, outcome = m["Winner"], m["Loser"], 1
            r1, r2, pt1, pt2 = m["WRank"], m["LRank"], m.get("WPts"), m.get("LPts")
        else:
            p1, p2, outcome = m["Loser"], m["Winner"], 0
            r1, r2, pt1, pt2 = m["LRank"], m["WRank"], m.get("LPts"), m.get("WPts")

        rows.append(store.features(p1, p2, m["Surface"], m["Tournament"], m["Round"],
                                   rank1=r1, rank2=r2, pts1=pt1, pts2=pt2))
        labels.append(outcome)
        dates.append(m["Date"])
        store.update(m)  # mise à jour APRÈS calcul (anti-fuite)

    X = pd.DataFrame(rows, columns=FEATURES)
    y = pd.Series(labels, name="outcome")
    return X, y, pd.Series(dates, name="date"), store


def build_backtest_matrix(df: pd.DataFrame):
    """
    Rejoue les matchs en orientation "gagnant = joueur1" (déterministe, sans
    randomisation) pour le backtest de l'onglet Challenge.

    Retourne (X, meta) : X = features PRÉ-MATCH orientées gagnant, meta = infos
    lisibles (date, joueurs, contexte). La probabilité prédite par le modèle
    pour la classe 1 = probabilité qu'il attribuait au VRAI vainqueur ; la
    prédiction est correcte si cette probabilité >= 0,5.
    """
    store = PlayerFormStore()
    rows, meta = [], []
    for _, m in df.iterrows():
        rows.append(store.features(m["Winner"], m["Loser"], m["Surface"],
                                   m["Tournament"], m["Round"],
                                   rank1=m["WRank"], rank2=m["LRank"],
                                   pts1=m.get("WPts"), pts2=m.get("LPts")))
        meta.append({
            "date": m["Date"].strftime("%Y-%m-%d"),
            "year": int(m["Date"].year),
            "tour": m["Tour"],
            "tournament": m["Tournament"],
            "surface": m["Surface"],
            "round": m["Round"],
            "winner": m["Winner"],
            "loser": m["Loser"],
        })
        store.update(m)
    return pd.DataFrame(rows, columns=FEATURES), pd.DataFrame(meta)
