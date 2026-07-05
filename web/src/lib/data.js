// Couche d'accès aux données statiques (JSON générés par le pipeline Python).
// Chaque fichier n'est téléchargé qu'UNE fois puis mis en cache mémoire
// (la promesse est mémoïsée) -> navigation entre onglets instantanée.

const cache = {}

export function loadJSON(name) {
  if (!cache[name]) {
    cache[name] = fetch(`${import.meta.env.BASE_URL}data/${name}`).then((r) => {
      if (!r.ok) throw new Error(`Chargement impossible : ${name}`)
      return r.json()
    })
  }
  return cache[name]
}
