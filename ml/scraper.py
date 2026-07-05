"""
ml/scraper.py — Mise à jour de l'historique des matchs (100 % fichiers).

Rôle : GitHub Actions (CRON) ─► python -m ml.scraper

tennis-data.co.uk publie un fichier Excel par saison. Pendant une saison en
cours, ce fichier est ENRICHI au fil des tournois. On re-télécharge donc les
saisons récentes (par défaut l'année en cours et la précédente), on en extrait
les matchs du Grand Chelem, et on les fusionne (UPSERT dédupliqué) dans
`data/grand_slams_all.csv`.

Le calendrier des matchs à venir (`data/upcoming.csv`) est un fichier éditable
(schéma documenté en tête du CSV). Le scraper se contente d'en garantir
l'existence ; on peut y brancher une vraie source de fixtures plus tard.

Sortie committée par le workflow : data/grand_slams_all.csv
"""

from __future__ import annotations

import io
import time
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

warnings.filterwarnings("ignore")  # bruit openpyxl "unknown extension"

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
COMBINED = DATA / "grand_slams_all.csv"
UPCOMING = DATA / "upcoming.csv"

BASE = "http://www.tennis-data.co.uk"
TOURS = {"ATP": "", "WTA": "w"}          # suffixe d'URL du dossier annuel
CATEGORY_COLS = ("Series", "Tier")       # ATP="Series", WTA="Tier"
GRAND_SLAM = "Grand Slam"
HEADERS = {"User-Agent": "Mozilla/5.0 (tennis-pipeline)"}

# Colonnes minimales conservées lors de la fusion (celles utilisées en aval).
KEEP = ["Tour", "Year", "Date", "Tournament", "Surface", "Round", "Best of",
        "Winner", "Loser", "WRank", "LRank", "WPts", "LPts", "AvgW", "AvgL"]
DEDUP_KEYS = ["Date", "Winner", "Loser", "Tournament"]


def _looks_like_excel(content: bytes) -> bool:
    # xlsx = magie ZIP "PK" ; xls = magie OLE ; page d'erreur serveur = "<html>".
    return content[:2] == b"PK" or content[:4] == b"\xd0\xcf\x11\xe0"


def fetch_season(year: int, tour: str, suffix: str) -> pd.DataFrame | None:
    """Télécharge une saison et renvoie les matchs du Grand Chelem, sinon None."""
    stem = f"{BASE}/{year}{suffix}/{year}"
    for url in (f"{stem}.xlsx", f"{stem}.xls"):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
        except requests.RequestException:
            continue
        if resp.status_code == 200 and _looks_like_excel(resp.content):
            df = pd.read_excel(io.BytesIO(resp.content))
            col = next((c for c in CATEGORY_COLS if c in df.columns), None)
            if col is None:
                return None
            gs = df[df[col] == GRAND_SLAM].copy()
            if gs.empty:
                return None
            gs.insert(0, "Tour", tour)
            gs.insert(1, "Year", year)
            return gs
    return None


def refresh_history(years: list[int]) -> int:
    """Fusionne les saisons `years` dans le CSV combiné. Renvoie le nb de lignes ajoutées."""
    frames = []
    for tour, suffix in TOURS.items():
        for year in years:
            gs = fetch_season(year, tour, suffix)
            if gs is not None:
                print(f"  [{tour} {year}] {len(gs)} matchs Grand Chelem")
                frames.append(gs)
            time.sleep(1.0)  # courtoisie serveur

    if not frames:
        print("  aucune donnée récente récupérée")
        return 0

    fresh = pd.concat(frames, ignore_index=True)
    before = 0
    if COMBINED.exists():
        existing = pd.read_csv(COMBINED, low_memory=False)
        before = len(existing)
        combined = pd.concat([existing, fresh], ignore_index=True)
    else:
        combined = fresh

    # UPSERT : on garde la dernière occurrence de chaque match (données à jour).
    combined["Date"] = pd.to_datetime(combined["Date"], errors="coerce")
    combined = (combined.dropna(subset=["Date", "Winner", "Loser"])
                        .drop_duplicates(subset=DEDUP_KEYS, keep="last")
                        .sort_values("Date")
                        .reset_index(drop=True))
    combined.to_csv(COMBINED, index=False)
    added = len(combined) - before
    print(f"  historique : {len(combined)} matchs (+{max(added, 0)} nouveaux)")
    return max(added, 0)


def ensure_upcoming() -> None:
    """Garantit l'existence du fichier des matchs à venir (éditable)."""
    if UPCOMING.exists():
        return
    print("  data/upcoming.csv absent : création d'un gabarit vide")
    pd.DataFrame(columns=[
        "id", "date", "tournament", "surface", "round", "best_of",
        "player1", "player2",
    ]).to_csv(UPCOMING, index=False)


def main() -> None:
    DATA.mkdir(exist_ok=True)
    current = datetime.utcnow().year
    years = [current - 1, current]  # saison en cours + précédente
    print(f"[scraper] rafraîchissement des saisons {years}")
    refresh_history(years)
    ensure_upcoming()
    print("[scraper] terminé.")


if __name__ == "__main__":
    main()
