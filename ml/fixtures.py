"""
ml/fixtures.py — Calendrier ET résultats en direct (tennisexplorer.com).

Rôle : GitHub Actions (CRON) ─► python -m ml.fixtures   (avant ml.predict / ml.track)

Problème résolu : tennis-data.co.uk (l'historique) publie les résultats avec du
RETARD. Un match joué aujourd'hui n'y figure pas avant plusieurs jours, donc
une prédiction resterait « en attente » trop longtemps. On récupère donc les
résultats depuis la MÊME source que les pronostics (tennisexplorer), le jour
même, pour que la vérification suive au jour le jour.

Deux sorties :
  data/upcoming.csv      -> matchs de Grand Chelem À VENIR (pas encore joués)
  data/live_results.csv  -> matchs de Grand Chelem TERMINÉS (avec vainqueur),
                            accumulés jour après jour (dédupliqués)

Robustesse : en cas d'échec réseau/parsing, on ne touche pas aux fichiers
existants (repli). Le pipeline reste fonctionnel.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
UPCOMING = ROOT / "data" / "upcoming.csv"
RESULTS = ROOT / "data" / "live_results.csv"
MODEL_PATH = ROOT / "models" / "model.joblib"

BASE = "https://www.tennisexplorer.com"
PAGES = {"ATP": "atp-single", "WTA": "wta-single"}
HEADERS = {"User-Agent": "Mozilla/5.0 (tennis-pipeline)"}

SLAM = {"wimbledon": "Wimbledon", "french open": "French Open",
        "roland garros": "French Open", "us open": "US Open",
        "australian open": "Australian Open"}
SURFACE = {"Wimbledon": "Grass", "French Open": "Clay",
           "US Open": "Hard", "Australian Open": "Hard"}

# Un token = en-tête de tournoi | nom de joueur | cellule "result" (sets gagnés).
TOKEN_RE = re.compile(
    r'(head flags.*?colspan[^>]*>(?P<tourn>.*?)</td>)'
    r'|(<td class="t-name"><a href="/player/[a-z0-9-]+/">(?P<player>[^<]+)</a>)'
    r'|(<td class="result">(?P<result>[^<]*)</td>)',
    re.S,
)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def known_players() -> dict[str, str]:
    """{clé normalisée -> nom canonique} depuis le modèle (pour mapper les noms)."""
    if not MODEL_PATH.exists():
        return {}
    return {_norm(n): n for n in joblib.load(MODEL_PATH)["store"].players}


def parse_matches(html: str) -> list[dict]:
    """
    Extrait les matchs de Grand Chelem. Chaque match = 2 joueurs consécutifs
    avec leur nombre de sets gagnés (cellule 'result'). Vainqueur = plus de sets ;
    None si le match n'est pas encore joué.
    """
    by_tourney: dict[str, list[list]] = {}
    current = None
    for tk in TOKEN_RE.finditer(html):
        if tk.group("tourn") is not None:
            current = re.sub("<[^>]+>", "", tk.group("tourn")).replace("\xa0", " ").strip()
            by_tourney.setdefault(current, [])
        elif tk.group("player") is not None and current is not None:
            by_tourney[current].append([tk.group("player").strip(), None])
        elif tk.group("result") is not None and current and by_tourney[current]:
            val = tk.group("result").strip()
            by_tourney[current][-1][1] = int(val) if val.isdigit() else None

    matches = []
    for label, items in by_tourney.items():
        slam = next((SLAM[k] for k in SLAM if k in label.lower()), None)
        if not slam:
            continue
        for i in range(0, len(items) - 1, 2):
            (n1, r1), (n2, r2) = items[i], items[i + 1]
            winner = None
            if r1 is not None and r2 is not None and r1 != r2:
                winner = n1 if r1 > r2 else n2
            matches.append({"slam": slam, "n1": n1, "n2": n2, "winner": winner})
    return matches


def _get(kind: str, page: str, day: datetime | None = None) -> str | None:
    """Récupère une page (matches=calendrier, results=résultats), pour un jour donné."""
    url = f"{BASE}/{kind}/?type={page}"
    if day is not None:
        url += f"&year={day.year}&month={day.month}&day={day.day}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
        return r.text
    except requests.RequestException as exc:
        print(f"[fixtures] échec {url} : {exc}")
        return None


def collect_upcoming(lookup: dict, ahead: int = 4) -> pd.DataFrame | None:
    """
    Matchs à venir (non joués) sur AUJOURD'HUI + les `ahead` jours suivants.

    On balaie plusieurs jours car, au moment du scrape, les matchs du jour sont
    souvent déjà joués : les vrais « à venir » sont ceux d'aujourd'hui (fin de
    journée) et des jours suivants, dont l'ordre du jeu est publié à l'avance.
    """
    rows = []
    start = datetime.now(timezone.utc)
    for tour, page in PAGES.items():
        for d in range(ahead + 1):
            day = start + timedelta(days=d)
            html = _get("matches", page, day)
            if not html:
                continue
            for m in parse_matches(html):
                if m["winner"] is not None:
                    continue  # déjà joué -> pas "à venir"
                p1, p2 = lookup.get(_norm(m["n1"])), lookup.get(_norm(m["n2"]))
                if not p1 or not p2 or p1 == p2:
                    continue
                rows.append({
                    "id": f"{m['slam'][:3].lower()}-{_norm(p1)}-{_norm(p2)}",
                    "date": day.strftime("%Y-%m-%d"), "tournament": m["slam"],
                    "surface": SURFACE[m["slam"]], "round": "",
                    "best_of": 5 if tour == "ATP" else 3,
                    "player1": p1, "player2": p2,
                })
    if not rows:
        return None
    return pd.DataFrame(rows).drop_duplicates(subset=["player1", "player2"])


def collect_results(lookup: dict, days: int = 5) -> pd.DataFrame | None:
    """Résultats terminés (avec vainqueur) des `days` derniers jours.

    Un recul de plusieurs jours rattrape les runs éventuellement manqués : une
    prédiction reste vérifiable même si le CRON a sauté un jour.
    """
    rows = []
    today = datetime.now(timezone.utc)
    for tour, page in PAGES.items():
        for d in range(days):
            day = today - timedelta(days=d)
            html = _get("results", page, day)
            if not html:
                continue
            for m in parse_matches(html):
                if m["winner"] is None:
                    continue
                loser_raw = m["n2"] if m["winner"] == m["n1"] else m["n1"]
                w = lookup.get(_norm(m["winner"]), m["winner"])
                l = lookup.get(_norm(loser_raw), loser_raw)
                rows.append({"date": day.strftime("%Y-%m-%d"),
                             "tournament": m["slam"], "winner": w, "loser": l})
    return pd.DataFrame(rows) if rows else None


def main() -> None:
    lookup = known_players()
    if not lookup:
        print("[fixtures] modèle indisponible : abandon.")
        return
    # --- Matchs à venir (aujourd'hui + jours suivants) ---
    up = collect_upcoming(lookup)
    if up is not None and not up.empty:
        up.to_csv(UPCOMING, index=False)
        print(f"[fixtures] {len(up)} matchs à venir -> {UPCOMING.name}")
    else:
        print("[fixtures] aucun match à venir exploitable — upcoming.csv conservé.")

    # --- Résultats terminés (fusion dédupliquée avec l'existant) ---
    res = collect_results(lookup)
    if res is not None and not res.empty:
        if RESULTS.exists():
            res = pd.concat([pd.read_csv(RESULTS), res], ignore_index=True)
        res = res.drop_duplicates(subset=["tournament", "winner", "loser"], keep="last")
        res.to_csv(RESULTS, index=False)
        print(f"[fixtures] {len(res)} résultats en direct -> {RESULTS.name}")
    else:
        print("[fixtures] aucun résultat récupéré — live_results.csv conservé.")


if __name__ == "__main__":
    main()
