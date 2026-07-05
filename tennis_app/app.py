"""
Application temps réel de prédiction de matchs du Grand Chelem.

Lancement :  streamlit run tennis_app/app.py

Choisis deux joueurs et le contexte du match : l'app calcule, à partir de la
forme actuelle de chaque joueur, la probabilité de victoire de chacun.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit runs this file as a script, so the project root is not on sys.path.
# Add it so `import tennis_app` works (also required to unpickle the store).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import pandas as pd
import streamlit as st

from tennis_app.features import FEATURES, PlayerFormStore  # noqa: E402,F401

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"

st.set_page_config(page_title="Grand Slam Predictor", page_icon="🎾", layout="centered")


@st.cache_resource
def load_artifacts():
    model = joblib.load(ARTIFACTS / "model.joblib")
    store = joblib.load(ARTIFACTS / "store.joblib")
    meta = joblib.load(ARTIFACTS / "meta.joblib")
    return model, store, meta


def form_badges(results: list[int]) -> str:
    """Render the last matches as coloured V/D badges (most recent on the right)."""
    if not results:
        return "_aucun match_"
    return " ".join("🟢" if r == 1 else "🔴" for r in results)


def player_panel(store: PlayerFormStore, name: str) -> dict:
    s = store.summary(name)
    rank = "—" if pd.isna(s["rank"]) else int(s["rank"])
    wr = "—" if s["win_rate"] != s["win_rate"] else f"{s['win_rate']*100:.0f}%"
    st.metric("Classement", rank)
    st.caption(f"Matchs joués : **{s['matches']}**  ·  Victoires : **{wr}**")
    st.caption("Forme récente : " + form_badges(s["form_last10"]))
    return s


def main() -> None:
    if not (ARTIFACTS / "model.joblib").exists():
        st.error("Modèle introuvable. Lance d'abord :  `python -m tennis_app.train`")
        st.stop()

    model, store, meta = load_artifacts()

    st.title("🎾 Prédiction de matchs du Grand Chelem")
    st.caption(f"Modèle entraîné sur les matchs {meta['trained_on']} "
               f"({len(meta['players'])} joueurs).")

    players = meta["players"]

    # --- Match context ---
    c1, c2 = st.columns(2)
    tournament = c1.selectbox("Tournoi", meta["tournaments"])
    default_surface = meta["surface_of_tournament"].get(tournament, meta["surfaces"][0])
    surface = c2.selectbox(
        "Surface", meta["surfaces"], index=meta["surfaces"].index(default_surface)
    )
    c3, c4 = st.columns(2)
    rnd = c3.selectbox("Tour", meta["rounds"])
    best_of = c4.selectbox("Format", ["3 sets", "5 sets"], index=1)  # informatif

    st.divider()

    # --- Player selection + form panels ---
    left, right = st.columns(2)
    with left:
        p1 = st.selectbox("Joueur 1", players,
                          index=players.index("Djokovic N.") if "Djokovic N." in players else 0)
        s1 = player_panel(store, p1)
    with right:
        default2 = "Nadal R." if "Nadal R." in players and "Nadal R." != p1 else players[1]
        p2 = st.selectbox("Joueur 2", players, index=players.index(default2))
        s2 = player_panel(store, p2)

    if p1 == p2:
        st.warning("Choisis deux joueurs différents.")
        st.stop()

    st.divider()
    if not st.button("Prédire le résultat", type="primary", use_container_width=True):
        return

    # --- Build features from CURRENT form and predict ---
    feats = store.features(p1, p2, surface, tournament, rnd)
    X = pd.DataFrame([[feats[f] for f in FEATURES]], columns=FEATURES)
    prob_p1 = float(model.predict_proba(X)[0, 1])
    prob_p2 = 1.0 - prob_p1

    st.subheader("Probabilités de victoire")
    r1, r2 = st.columns(2)
    r1.metric(p1, f"{prob_p1*100:.1f}%")
    r2.metric(p2, f"{prob_p2*100:.1f}%")
    st.progress(prob_p1, text=f"{p1} {prob_p1*100:.0f}%  —  {prob_p2*100:.0f}% {p2}")

    favourite = p1 if prob_p1 >= prob_p2 else p2
    edge = abs(prob_p1 - prob_p2)
    st.success(f"Favori : **{favourite}**  (écart {edge*100:.0f} points)")

    # Fair decimal odds implied by the model (1 / probability).
    with st.expander("Détails (cotes implicites & features)"):
        st.write(f"Cote équitable {p1} : **{1/prob_p1:.2f}**  ·  "
                 f"{p2} : **{1/prob_p2:.2f}**")
        st.caption("Différences de features utilisées (joueur1 − joueur2) :")
        st.dataframe(
            pd.DataFrame({"feature": FEATURES, "valeur": [feats[f] for f in FEATURES]}),
            hide_index=True, use_container_width=True,
        )
        st.caption("`NaN` = pas encore d'historique pour ce joueur sur ce critère "
                   "(la valeur médiane est utilisée par le modèle).")


if __name__ == "__main__":
    main()
