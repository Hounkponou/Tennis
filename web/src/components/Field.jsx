// Petit <select> étiqueté, réutilisable dans tous les filtres.
export function Select({ label, value, onChange, options, allLabel }) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      {label && <span className="text-lo">{label}</span>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="glass rounded-lg px-3 py-2 text-sm text-hi outline-none
          focus:ring-1 focus:ring-brand"
      >
        {allLabel && <option value="">{allLabel}</option>}
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </label>
  )
}

// Contrôle segmenté (ex : Tous / ATP / WTA).
export function Segmented({ value, onChange, options }) {
  return (
    <div className="glass inline-flex gap-1 p-1">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition
            ${value === o.value ? 'bg-brand text-slate-900' : 'text-mid hover-surface'}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
