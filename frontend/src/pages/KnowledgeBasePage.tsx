import { useQuery, useSuspenseQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'
import { ArticleFilters } from '../features/knowledge-base/ArticleFilters'
import { applySelection, emptySelection, hasSelection } from '../features/knowledge-base/facets'
import { ArticleRow } from '../features/knowledge-base/ArticleRow'
import { q } from '../shared/api/queries'
import { SearchInput } from '../shared/ui/SearchInput'

const isRecent = (updated: string) => /Saturday|days? ago|weeks? ago/.test(updated)

export function KnowledgeBasePage() {
  const { data: articles } = useSuspenseQuery(q.articles)
  const [text, setText] = useState('')
  const [sel, setSel] = useState(emptySelection)
  // ponytail: ranks on every keystroke; debounce once search hits the network.
  const ranked = useQuery({ ...q.articleSearch(text), enabled: !!text, placeholderData: (prev) => prev }).data

  const active = !!text || hasSelection(sel)
  const shown = active ? applySelection(text && ranked ? ranked : articles, sel) : articles.filter((a) => isRecent(a.updated))

  return (
    <section className="kb">
      <h1 className="display sm">Knowledge Base</h1>
      <SearchInput id="kbq" label="Search the knowledge base" value={text} onChange={setText} placeholder="e.g., Cannot connect to my cluster" />
      <div className="kb-grid">
        <ArticleFilters articles={articles} sel={sel} onChange={setSel} />
        <section className="card results" aria-live="polite">
          <h2 className="h3">{active ? `${shown.length} results` : 'Recently Published Articles'}</h2>
          {shown.map((a) => <ArticleRow key={a.id} a={a} />)}
          {!shown.length && <p className="meta">No articles match. Try fewer filters, or <Link to="/help">ask the assistant</Link>.</p>}
        </section>
      </div>
    </section>
  )
}
