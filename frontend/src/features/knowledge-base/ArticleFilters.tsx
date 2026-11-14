import { useState } from 'react'
import type { Article } from '../../shared/api/articles'
import { Icon } from '../../shared/ui/Icon'
import { ICONS } from '../../shared/ui/icons'
import { FACETS, type FacetKey, type Selection } from './facets'

/** Checkbox facets with counts over the whole corpus. */
export function ArticleFilters({ articles, sel, onChange }: { articles: Article[]; sel: Selection; onChange: (s: Selection) => void }) {
  const [more, setMore] = useState<Partial<Record<FacetKey, boolean>>>({})
  const toggle = (k: FacetKey, v: string) => {
    const s = new Set(sel[k])
    if (!s.delete(v)) s.add(v)
    onChange({ ...sel, [k]: s })
  }

  return (
    <aside className="filters" aria-label="Filters">
      <p className="filter-h"><Icon d={ICONS.filter} size={16} /> FILTER</p>
      {FACETS.map((f) => {
        const counts = new Map<string, number>()
        articles.forEach((a) => counts.set(a[f.key], (counts.get(a[f.key]) ?? 0) + 1))
        const vals = [...counts].sort((x, y) => y[1] - x[1])
        return (
          <fieldset key={f.key}>
            <legend>{f.label.toUpperCase()}</legend>
            {vals.slice(0, more[f.key] ? undefined : 5).map(([v, n]) => (
              <label key={v} className="check">
                <input type="checkbox" checked={sel[f.key].has(v)} onChange={() => toggle(f.key, v)} />
                {(f.name ?? String)(v)} ({n})
              </label>
            ))}
            {vals.length > 5 && (
              <button className="link-btn" onClick={() => setMore({ ...more, [f.key]: !more[f.key] })}>
                {more[f.key] ? 'SHOW LESS ▴' : 'SHOW MORE ▾'}
              </button>
            )}
          </fieldset>
        )
      })}
    </aside>
  )
}
