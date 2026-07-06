"""
ml/fixtures.py — Récupération d'un VRAI calendrier de matchs à venir.

Rôle : GitHub Actions (CRON) ─► python -m ml.fixtures   (avant ml.predict)

tennis-data.co.uk ne fournit pas de calendrier ; on scrape donc la grille du
jour de tennisexplorer.com (gratuit), on isole les matchs de Grand Chelem, et
on ne garde que ceux dont LES DEUX joueurs sont connus du modèle (sinon la
prédiction n'aurait pas de sens). Le résultat écrase data/upcoming.csv.

Robustesse : en cas d'échec réseau, de parsing vide, ou d'aucun match
exploitable, on NE TOUCHE PAS au fichier existant (repli sur le calendrier
manuel). Le pipeline reste donc toujours fonctionnel.

Nuance noms : tennisexplorer écrit "Auger Aliassime F." là où tennis-data écrit
"Auger-Aliassime F.". On normalise (minuscules, sans espaces/tirets/points)
pour faire correspondre les joueurs au référentiel du modèle.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
UPCOMING = ROOT / "data" / "upcoming.csv"
MODEL_PATH = ROOT / "models" / "model.joblib"

BASE = "https://www.tennisexplorer.com/matches/?type="
PAGES = {"ATP": "atp-single", "WTA": "wta-single"}
HEADERS = {"User-Agent": "Mozilla/5.0 (tennis-pipeline)"}

# Correspondance des libellés tournoi -> nom canonique + surface + format.
SLAM = {"wimbledon": "Wimbledon", "french open": "French Open",
        "roland garros": "French Open", "us open": "US Open",
        "australian open": "Australian Open"}
SURFACE = {"Wimbledon": "Grass", "French Open": "Clay",
           "US Open": "Hard", "Australian Open": "Hard"}

# Un token = soit un en-tête de tournoi, soit un lien joueur (nom affiché).
TOKEN_RE = re.compile(
    r'(head flags.*?colspan[^>]*>(?P<tourn>.*?)</td>)'
    r'|(/player/[a-z0-9-]+/"[^>]*>(?P<player>[^<]+)</a>)',
    re.S,
)


def _norm(name: str) -> str:
    """Clé de correspondance robuste (min., sans espaces/tirets/points/accents)."""
    return re.sub(r"[^a-z]", "", name.lower())


def known_players() -> dict[str, str]:
    """Retourne {clé normalisée -> nom canonique} depuis le modèle entraîné."""
    if not MODEL_PATH.exists():
        return {}
    store = joblib.load(MODEL_PATH)["store"]
    return {_norm(n): n for n in store.players}


def parse_page(html: str) -> list[tuple[str, str]]:
    """Extrait les paires (joueur1, joueur2) par tournoi de Grand Chelem."""
    by_tourney: dict[str, list[str]] = {}
    current = None
    for tk in TOKEN_RE.finditer(html):
        if tk.group("tourn") is not None:
            label = re.sub("<[^>]+>", "", tk.group("tourn")).replace("\xa0", " ").strip()
            current = label
            by_tourney.setdefault(current, [])
        elif current is not None:
            by_tourney[current].append(tk.group("player").strip())

    pairs = []
    for label, names in by_tourney.items():
        slam = next((SLAM[k] for k in SLAM if k in label.lower()), None)
        if not slam:
            continue
        # Les joueurs sont listés match par match : on les apparie 2 à 2.
        for i in range(0, len(names) - 1, 2):
            pairs.append((slam, names[i], names[i + 1]))
    return pairs


def fetch_fixtures() -> pd.DataFrame | None:
    """Construit le DataFrame des matchs à venir exploitables, ou None si échec."""
    lookup = known_players()
    if not lookup:
        print("[fixtures] modèle indisponible : impossible de mapper les joueurs.")
        return None

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = []
    for tour, page in PAGES.items():
        try:
            resp = requests.get(BASE + page, headers=HEADERS, timeout=25)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[fixtures] échec de récupération {tour} : {exc}")
            continue

        best_of = 5 if tour == "ATP" else 3
        for slam, p1_raw, p2_raw in parse_page(resp.text):
            p1 = lookup.get(_norm(p1_raw))
            p2 = lookup.get(_norm(p2_raw))
            if not p1 or not p2 or p1 == p2:
                continue  # on n'garde que les matchs à 2 joueurs connus
            rows.append({
                "id": f"{slam[:3].lower()}-{_norm(p1)}-{_norm(p2)}",
                "date": today,
                "tournament": slam,
                "surface": SURFACE[slam],
                "round": "",              # non fourni par la grille (imputé par le modèle)
                "best_of": best_of,
                "player1": p1,
                "player2": p2,
            })

    if not rows:
        return None
    df = pd.DataFrame(rows).drop_duplicates(subset=["player1", "player2"])
    return df


def main() -> None:
    df = fetch_fixtures()
    if df is None or df.empty:
        print("[fixtures] aucun match exploitable — on conserve upcoming.csv existant.")
        return
    df.to_csv(UPCOMING, index=False)
    print(f"[fixtures] {len(df)} matchs à venir écrits -> {UPCOMING.relative_to(ROOT)}")
    for _, r in df.iterrows():
        print(f"   {r['tournament']:>15} | {r['player1']} vs {r['player2']}")


if __name__ == "__main__":
    main()
