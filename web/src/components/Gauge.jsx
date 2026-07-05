import { RadialBarChart, RadialBar, PolarAngleAxis } from 'recharts'

/**
 * Jauge circulaire (Recharts) affichant la probabilité de victoire du favori.
 * - value : probabilité du favori en pourcentage (0-100)
 * - color : couleur de l'arc
 * Composant "pur" (aucun état) -> rapide et réutilisable.
 */
export default function Gauge({ value, color = '#22d3ee', size = 120 }) {
  const data = [{ name: 'proba', value }]
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <RadialBarChart
        width={size}
        height={size}
        cx="50%"
        cy="50%"
        innerRadius="72%"
        outerRadius="100%"
        barSize={10}
        data={data}
        startAngle={90}
        endAngle={-270}
      >
        {/* L'échelle 0-100 est fixée par PolarAngleAxis (sinon Recharts l'auto-scale). */}
        <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
        <RadialBar background={{ fill: 'var(--c-surf2)' }}
                   dataKey="value" cornerRadius={8} fill={color} />
      </RadialBarChart>
      {/* Valeur au centre de la jauge */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold tabular-nums">{Math.round(value)}%</span>
        <span className="text-[10px] uppercase tracking-wide text-lo">favori</span>
      </div>
    </div>
  )
}
