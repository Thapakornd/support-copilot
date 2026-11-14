import { Link } from '@tanstack/react-router'

/** Generic "nothing here" block; pages pass their own title and way back. */
export function NotFound({ title, back = '/', backLabel = 'Go home' }: { title: string; back?: '/' | '/kb' | '/cases'; backLabel?: string }) {
  return (
    <section className="page narrow center stack">
      <h1 className="h2">{title}</h1>
      <Link className="btn" to={back}>{backLabel}</Link>
    </section>
  )
}
