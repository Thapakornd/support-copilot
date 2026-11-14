export function StatRow({ stats }: { stats: [label: string, value: number][] }) {
  return (
    <div className="stats">
      {stats.map(([k, v]) => (
        <div key={k} className="card stat"><span className="meta">{k}</span><b>{v}</b></div>
      ))}
    </div>
  )
}
