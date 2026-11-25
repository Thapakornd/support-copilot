import { useQuery } from '@tanstack/react-query'
import { Link, getRouteApi } from '@tanstack/react-router'
import { useState, type FormEvent } from 'react'
import { AnswerPanel } from '../features/assistant/AnswerPanel'
import { useAsk } from '../features/assistant/useAsk'
import { PagedArticles } from '../features/knowledge-base/PagedArticles'
import { ApiError } from '../shared/api/client'
import { q } from '../shared/api/queries'
import { catName } from '../shared/config/categories'
import { sourceUrl } from '../shared/lib/sourceUrl'
import { Icon } from '../shared/ui/Icon'
import { ICONS } from '../shared/ui/icons'

const route = getRouteApi('/help/$category')

export function AskPage() {
  const param = route.useParams().category
  const category = param === 'any' ? undefined : param
  const [text, setText] = useState('')
  const ask = useAsk(category)
  const res = ask.data
  const question = ask.variables
  const { data: related } = useQuery({ ...q.articleSearch(question ?? '', category), enabled: !!question })
  const invalid = ask.error instanceof ApiError && ask.error.status === 422
  const caseAnswer = res?.status === 'answered' ? res.answer : ''
  const caseSources = res?.sources.map(({ document_id, title, source_url }) => ({ id: document_id, title, url: sourceUrl(source_url) })) ?? []

  function submit(e: FormEvent) {
    e.preventDefault()
    if (text.trim() && !ask.isPending) ask.mutate(text.trim())
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
      <p className="meta fine">Remove passwords and connection-string credentials first.</p>

      {ask.isPending && <div className="answer pending" aria-live="polite">Searching published articles and composing an answer…</div>}

      {res && <AnswerPanel key={ask.submittedAt} res={res} />}
      {ask.isError && (
        <div className="answer pending stack">
          <p role="alert">{invalid ? 'Check the category and try a shorter question.' : 'The answer service is unavailable. Try again.'}</p>
          {!invalid && question && <button type="button" className="btn sm" onClick={() => ask.mutate(question)}>Retry</button>}
        </div>
      )}
      {!!related?.length && (
        <>
          <h2 className="h3">Related articles</h2>
          <PagedArticles key={question} articles={related} />
        </>
      )}
      {question && (res || ask.isError) && (
        <div className="center stack">
          <h2 className="h3">Didn’t find what you were looking for?</h2>
          <Link className="btn pri" to="/case" state={{ caseDraft: { question, category, answer: caseAnswer, sources: caseSources } }}>
            Create a case
          </Link>
        </div>
      )}
    </section>
  )
}
