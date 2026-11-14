import { useSuspenseQuery } from '@tanstack/react-query'
import { Link, getRouteApi } from '@tanstack/react-router'
import { useState } from 'react'
import { q } from '../shared/api/queries'
import { catName } from '../shared/config/categories'
import { Icon } from '../shared/ui/Icon'
import { ICONS } from '../shared/ui/icons'
import { NotFound } from '../shared/ui/NotFound'

const route = getRouteApi('/kb/$articleId')

export function ArticlePage() {
  const { articleId } = route.useParams()
  const { data: a } = useSuspenseQuery(q.article(articleId))
  const { data: articles } = useSuspenseQuery(q.articles)
  const [vote, setVote] = useState<'up' | 'down' | null>(null)

  if (!a) return <NotFound title="Article not found" back="/kb" backLabel="Back to Knowledge Base" />
  const related = articles.filter((x) => x.topic === a.topic && x.id !== a.id)
  const topic = { category: a.topic }

  return (
    <section className="page wide">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/kb">Knowledge Base</Link> <span aria-hidden="true">›</span> <span>{catName(a.topic)}</span>
      </nav>
      <div className="case-grid">
        <article className="col">
          <p className="meta">Last update {a.updated} | <b>{a.type}</b> · {a.product}</p>
          <h1 className="display sm">{a.title}</h1>
          <section className="card pad">
            <h2 className="sec">Summary</h2>
            <p className="lead-p">{a.excerpt}</p>
          </section>
          {a.body && (
            <section className="card pad">
              <h2 className="sec">Steps</h2>
              <ol className="steps">{a.body.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
              {a.body.note && <p className="note"><b>Note:</b> {a.body.note}</p>}
            </section>
          )}
          <div className="card pad vote-row">
            <span>Was this article helpful?</span>
            <button className="btn sm" aria-pressed={vote === 'up'} onClick={() => setVote('up')}>Yes</button>
            <button className="btn sm" aria-pressed={vote === 'down'} onClick={() => setVote('down')}>No</button>
            {vote === 'down' && <span className="meta">Sorry about that. <Link to="/help/$category" params={topic}>Ask the assistant</Link> or <Link to="/case">create a case</Link>.</span>}
            {vote === 'up' && <span className="meta">Thanks for the feedback.</span>}
          </div>
        </article>
        <aside className="col side">
          <h2 className="h3">About this article</h2>
          <section className="card pad">
            <dl className="dl">
              <dt>Type</dt><dd>{a.type}</dd>
              <dt>Product</dt><dd>{a.product}</dd>
              <dt>Topic</dt><dd>{catName(a.topic)}</dd>
              <dt>Updated</dt><dd>{a.updated}</dd>
            </dl>
          </section>
          <h2 className="h3">Related articles</h2>
          <section className="card pad">
            <ul className="related">{related.map((r) => <li key={r.id}><Link to="/kb/$articleId" params={{ articleId: r.id }}>{r.title}</Link></li>)}</ul>
          </section>
          <Link className="btn pri" to="/help/$category" params={topic}><Icon d={ICONS.sparkle} size={16} /> Ask the assistant about {catName(a.topic)}</Link>
        </aside>
      </div>
    </section>
  )
}
