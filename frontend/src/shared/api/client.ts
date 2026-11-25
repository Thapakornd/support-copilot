import { identityHeader } from './identity'

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

/** The one place that talks HTTP. Throws on non-2xx; callers decide what a failure means. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...identityHeader(), ...init?.headers },
  })
  if (!r.ok) throw new ApiError(`${init?.method ?? 'GET'} ${path} → ${r.status}`, r.status)
  return r.json()
}

/** A missing resource is an answer, not a failure: 404 becomes null. */
export const orNull = <T>(request: Promise<T>): Promise<T | null> =>
  request.catch((e) => {
    if (e instanceof ApiError && e.status === 404) return null
    throw e
  })
