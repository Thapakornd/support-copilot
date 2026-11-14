const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

/** The one place that talks HTTP. Throws on non-2xx; callers decide what a failure means. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!r.ok) throw new Error(`${init?.method ?? 'GET'} ${path} → ${r.status}`)
  return r.json()
}
