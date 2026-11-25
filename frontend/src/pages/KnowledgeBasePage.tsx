import { useQuery, useSuspenseQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { ArticleFilters } from '../features/knowledge-base/ArticleFilters'
import { applySelection, emptySelection, hasSelection } from '../features/knowledge-base/facets'
import { ArticleRow } from '../features/knowledge-base/ArticleRow'
import { q } from '../shared/api/queries'
import { SearchInput } from '../shared/ui/SearchInput'

const RECENT = 10

export function KnowledgeBasePage() {
  const { data: articles } = useSuspenseQuery(q.articles)
  const [text, setText] = useState('')
  const [sel, setSel] = useState(emptySelection)
  const query = text.trim()
  const [settled, setSettled] = useState('') // the query once typing pauses
  useEffect(() => {
    const t = setTimeout(() => setSettled(query), 250)
    return () => clearTimeout(t)
  }, [query])
  const search = useQuery({ ...q.articleSearch(settled), enabled: !!settled, placeholderData: (prev) => prev })

  const active = !!query || hasSelection(sel)
  const ranked = query ? search.data ?? [] : articles // the API lists newest first
  const shown = active ? applySelection(ranked, sel) : articles.slice(0, RECENT)
  const failed = !!query && search.isError
  const searching = !!query && !failed && !search.data

  return (
    <section className="kb">
      <h1 className="display sm">Knowledge Base</h1>
      <SearchInput id="kbq" label="Search the knowledge base" value={text} onChange={setText} placeholder="e.g., Cannot connect to my cluster" />
      <div className="kb-grid">
        <ArticleFilters articles={articles} sel={sel} onChange={setSel} />
        <section className="card results" aria-live="polite">
          <h2 className="h3">{searching ? 'Searching…' : active ? `${shown.length} results` : 'Recently Published Articles'}</h2>
          {shown.map((a) => <ArticleRow key={a.id} a={a} />)}
          {failed && <p className="meta" role="alert">Search is unavailable. Try again.</p>}
          {!shown.length && !searching && !failed && <p className="meta">No articles match. Try fewer filters, or <Link to="/help">ask the assistant</Link>.</p>}
        </section>
      </div>
    </section>
  )
}
