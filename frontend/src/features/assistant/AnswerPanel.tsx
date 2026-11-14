import { Link } from '@tanstack/react-router'
import { useState } from 'react'
import type { Article } from '../../shared/api/articles'
import { Icon } from '../../shared/ui/Icon'
import { ICONS } from '../../shared/ui/icons'
import type { AskResult } from './useAsk'

/** Collapsible AI answer with its top references and a thumbs vote. */
export function AnswerPanel({ res, refs }: { res: AskResult; refs: Article[] }) {
  const [open, setOpen] = useState(true)
  const [vote, setVote] = useState<'up' | 'down' | null>(null)

  return (
    <section className="answer" aria-label="AI-generated answer">
      <button className="answer-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span><Icon d={ICONS.sparkle} size={16} /> AI-generated answer</span>
        {!res.live && <span className="tag">Demo · backend offline</span>}
        <Icon d={open ? ICONS.chevronUp : ICONS.chevronDown} />
      </button>
      {open && (
        <div className="answer-body">
          {res.answer.split('\n').filter(Boolean).map((p, i) => <p key={i}>{p}</p>)}
          <h3 className="sec">Referenced articles</h3>
          <ol className="refs">
            {refs.map((s) => <li key={s.id}><Link to="/kb/$articleId" params={{ articleId: s.id }}>{s.title}</Link></li>)}
          </ol>
          <div className="vote">
            <span>How was the response?</span>
            <button aria-label="Helpful" aria-pressed={vote === 'up'} onClick={() => setVote('up')}><Icon d={ICONS.thumbUp} size={16} /></button>
            <button aria-label="Not helpful" aria-pressed={vote === 'down'} onClick={() => setVote('down')}><Icon d={ICONS.thumbDown} size={16} /></button>
            {vote && <span className="meta">Thanks for the feedback.</span>}
          </div>
        </div>
      )}
    </section>
  )
}
