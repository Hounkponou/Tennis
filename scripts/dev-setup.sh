#!/usr/bin/env bash
#
# Configuration Git à lancer UNE FOIS après avoir cloné le repo :
#   bash scripts/dev-setup.sh
#
# Met en place le modèle « le pipeline CI possède les données » :
#  - stratégie de merge qui prend toujours la version du CI sur les fichiers générés
#  - hook pre-commit qui empêche de committer ces fichiers en local
#  - stratégie de pull par merge (évite l'erreur "divergent branches")
set -e
cd "$(dirname "$0")/.."

# Driver de merge "keep-ci" : sur conflit, garder la version entrante (CI).
git config merge.keep-ci.name "toujours prendre la version du pipeline CI"
git config merge.keep-ci.driver "cp -f '%B' '%A'"

# Utiliser les hooks versionnés du repo.
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true

# Tirer en mode merge (plus d'erreur "Need to specify how to reconcile...").
git config pull.rebase false

echo "✅ Setup dev terminé."
echo "   - Les fichiers data/, models/, web/public/data/ sont gérés par le CI."
echo "   - Tu ne committes que le code (ml/, web/src/, config)."
