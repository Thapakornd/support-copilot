// ponytail: demo categories; move to GET /categories if the list ever becomes editable.

export type Category = { id: string; name: string; blurb: string; icon: string }

export const CATEGORIES: Category[] = [
  { id: 'connectivity', name: 'Connectivity', blurb: 'Timeouts, IP access, peering, DNS', icon: 'M5 12a7 7 0 0 1 14 0M8 12a4 4 0 0 1 8 0M12 12v8' },
  { id: 'performance', name: 'Performance & memory', blurb: 'Slow ops, memory, cache pressure', icon: 'M4 19h16M7 16V9M12 16V5M17 16v-4' },
  { id: 'queries', name: 'Queries & indexes', blurb: 'Plans, index builds, aggregation', icon: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4' },
  { id: 'replication', name: 'Replication & sharding', blurb: 'Elections, lag, balancer', icon: 'M6 6h5v5H6zM13 13h5v5h-5zM8.5 11v4.5H13M15.5 13V8.5H11' },
  { id: 'security', name: 'Security & access', blurb: 'Users, roles, TLS, auth errors', icon: 'M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6z' },
  { id: 'backup', name: 'Backup & restore', blurb: 'Snapshots, PITR, restores', icon: 'M4 7h16v12H4zM8 7V5h8v2M9 13h6' },
  { id: 'drivers', name: 'Drivers & SDKs', blurb: 'Node.js, Python, Java, C#', icon: 'M8 8l-4 4 4 4M16 8l4 4-4 4M14 5l-4 14' },
]

export const catName = (id?: string) => CATEGORIES.find((c) => c.id === id)?.name ?? 'any'
