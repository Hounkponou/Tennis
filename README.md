# 🎾 Tennis Predictor

Application de prédiction des matchs du Grand Chelem (ATP & WTA) : pipeline de
données + modèle ML réentraîné automatiquement + frontend React.

## Architecture

```
data/            données (historique, matchs à venir, résultats en direct)  ← possédé par le CI
models/          modèle entraîné + métriques                                 ← possédé par le CI
ml/              pipeline Python (scraper, fixtures, retrain, predict, track, export_web)
web/             frontend React (Vite + Tailwind + Recharts)
  public/data/   JSON consommés par le frontend                              ← possédé par le CI
.github/workflows/pipeline.yml   CRON quotidien : scrape → retrain → fixtures → predict → track → export
```

## Mise en route (développeur)

```bash
git clone https://github.com/Hounkponou/Tennis.git
cd Tennis
bash scripts/dev-setup.sh          # configure Git (hooks + stratégie de merge)
pip install -r requirements.txt
cd web && npm install && npm run dev
```

## ⚠️ Règle d'or : le CI possède les données

Les dossiers **`data/`, `models/` et `web/public/data/`** sont générés et
committés **uniquement par le pipeline GitHub Actions**. En local :

- Tu ne committes **que le CODE** (`ml/`, `web/src/`, configs).
- Un hook `pre-commit` **bloque** tout commit de ces fichiers générés
  (contournable avec `git commit --no-verify` si vraiment nécessaire).
- En cas de conflit de merge sur ces fichiers, la version du CI est prise
  automatiquement (`.gitattributes` + driver `keep-ci`).

👉 Résultat : plus de divergences ni de conflits entre tes commits et ceux du
pipeline. Fais simplement un **`git pull`** avant de travailler.

## Le pipeline (automatique, quotidien)

1. `ml/scraper.py` — rafraîchit l'historique (tennis-data.co.uk).
2. `ml/fixtures.py` — calendrier à venir + résultats en direct (tennisexplorer.com).
3. `ml/retrain.py` — réentraîne le meilleur modèle si assez de nouveaux matchs.
4. `ml/predict.py` — prédit les matchs à venir.
5. `ml/track.py` — confronte prédictions et résultats réels (taux de réussite).
6. `ml/export_web.py` — génère les JSON du frontend.

Le push déclenche le redéploiement Vercel.
