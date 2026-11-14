import { Link } from '@tanstack/react-router'
import type { Ticket } from '../../shared/api/tickets'
import { fmt } from '../../shared/lib/format'
import { Icon } from '../../shared/ui/Icon'
import { ICONS } from '../../shared/ui/icons'

/** Description, the AI answer that failed, and the comment/event timeline. */
export function CommentThread({ ticket: t }: { ticket: Ticket }) {
  const replies = t.comments.filter((c) => c.role !== 'system').length
  return (
    <>
      <h2 className="h3">Description</h2>
      <section className="card pad"><p className="pre">{t.description ?? t.summary}</p></section>

      {t.aiAnswer && (
        <section className="card pad ai-box">
          <h3 className="sec ai-h"><Icon d={ICONS.sparkle} size={14} /> AI suggestion that did not resolve it</h3>
          <p className="pre">{t.aiAnswer}</p>
          {!!t.sources.length && (
            <ul className="refs">
              {t.sources.map((s) => <li key={s.title}>{s.id ? <Link to="/kb/$articleId" params={{ articleId: s.id }}>{s.title}</Link> : s.title}</li>)}
            </ul>
          )}
        </section>
      )}

      <h2 className="h3">Comments <span className="badge-n">{replies}</span></h2>
      {t.comments.map((c, i) => c.role === 'system'
        ? <p key={i} className="event"><Icon d={ICONS.clock} size={14} /> {c.body} · {fmt(c.at)}</p>
        : (
          <article key={i} className={`card pad comment ${c.role}`}>
            <p className="meta"><b className="who">{c.author}</b>{c.role === 'agent' && <span className="pill gray">Support</span>} posted on {fmt(c.at)}</p>
            <p className="pre">{c.body}</p>
          </article>
        ))}
    </>
  )
}
