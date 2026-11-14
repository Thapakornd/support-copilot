import { useSuspenseQuery } from '@tanstack/react-query'
import { Link, getRouteApi } from '@tanstack/react-router'
import { useState, type FormEvent } from 'react'
import { AnswerPanel } from '../features/assistant/AnswerPanel'
import { useAsk } from '../features/assistant/useAsk'
import { PagedArticles } from '../features/knowledge-base/PagedArticles'
import { q } from '../shared/api/queries'
import { catName } from '../shared/config/categories'
import { Icon } from '../shared/ui/Icon'
import { ICONS } from '../shared/ui/icons'

const route = getRouteApi('/help/$category')

export function AskPage() {
  const param = route.useParams().category
  const category = param === 'any' ? undefined : param
  const { data: articles } = useSuspenseQuery(q.articles)
  const [text, setText] = useState('')
  const ask = useAsk(category)
  const res = ask.data
  const refs = res?.sources.slice(0, 3) ?? []
  const scope = category ? catName(category) : 'all'
  const count = category ? articles.filter((a) => a.topic === category).length : articles.length

  function submit(e: FormEvent) {
    e.preventDefault()
    if (text.trim()) ask.mutate(text)
  }

  return (
    <section className="hero ask">
      <Link className="btn ghost sm back" to="/help"><Icon d={ICONS.arrowLeft} size={16} /> Back to categories</Link>
      <h1 className="h2">Please enter a short description of your</h1>
      <p className="h2"><span className="chip">{category ? catName(category) : 'General'}</span> issue below to start</p>

      <form className="askbox" onSubmit={submit} role="search">
        <label htmlFor="q" className="sr">Describe your issue</label>
        <input id="q" value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Node.js app times out after a VPC peering change" autoFocus />
        <button className="btn pri" disabled={ask.isPending}>{ask.isPending ? 'Searching…' : 'Ask'}</button>
      </form>
      <p className="meta fine">AI search over {category ? `${count} ${scope}` : count} articles. Remove passwords and connection-string credentials first.</p>

      {ask.isPending && <div className="answer pending" aria-live="polite">Searching {scope} articles and composing an answer…</div>}

      {res && !ask.isPending && (
        <>
          <AnswerPanel key={`answer-${ask.submittedAt}`} res={res} refs={refs} />
          <p className="meta center">Not helpful? Scroll down for related articles or open a case.</p>
          <PagedArticles key={`pages-${ask.submittedAt}`} articles={res.sources} />
          <div className="center stack">
            <h2 className="h3">Didn’t find what you were looking for?</h2>
            <Link className="btn pri" to="/case" state={{ caseDraft: { question: res.question, category, answer: res.answer, sources: refs.map(({ id, title }) => ({ id, title })) } }}>
              Create a case
            </Link>
          </div>
        </>
      )}
    </section>
  )
}
