import { useState } from 'react'
import { sourceUrl } from '../../shared/lib/sourceUrl'
import { Icon } from '../../shared/ui/Icon'
import { ICONS } from '../../shared/ui/icons'
import type { AskResult } from './useAsk'

export function AnswerPanel({ res }: { res: AskResult }) {
  const [open, setOpen] = useState(true)
  const [vote, setVote] = useState<'up' | 'down' | null>(null)
  const label = res.status === 'insufficient_evidence' ? 'More detail needed' : 'AI-generated answer'

  return (
    <section className="answer" aria-label={label}>
      <button className="answer-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span><Icon d={ICONS.sparkle} size={16} /> {label}</span>
        <Icon d={open ? ICONS.chevronUp : ICONS.chevronDown} />
      </button>
      {open && (
        <div className="answer-body">
          {res.answer.split('\n').filter(Boolean).map((p, i) => <p key={i}>{p}</p>)}
          {res.sources.length > 0 && (
            <>
              <h3 className="sec">Referenced articles</h3>
              <ol className="refs">
                {res.sources.map((source) => {
                  const url = sourceUrl(source.source_url)
                  return (
                    <li key={source.number} value={source.number}>
                      {url ? <a href={url} target="_blank" rel="noopener noreferrer">{source.title}</a> : source.title}
                      {source.heading_path.length > 0 && <span className="meta"> · {source.heading_path.join(' › ')}</span>}
                    </li>
                  )
                })}
              </ol>
            </>
          )}
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
