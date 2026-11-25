import Markdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { sourceUrl } from '../../shared/lib/sourceUrl'

// The docs' own links point at each page's raw markdown file; the web page is the same path with a slash.
const DOCS_MARKDOWN = /^(https:\/\/www\.mongodb\.com\/docs\/[^?#]+)\.md(?=#|$)/
const plugins = [remarkGfm]
const components: Components = {
  h1: ({ children }) => <h2>{children}</h2>, // the page already has its h1
  a: ({ href, children }) => href ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <>{children}</>,
  img: ({ src, alt }) => src ? <img src={src} alt={alt ?? ''} loading="lazy" /> : <>{alt}</>,
  table: ({ children }) => <div className="md-table" role="region" aria-label="Table" tabIndex={0}><table>{children}</table></div>,
}

/** Article markdown without its title line, which the page already shows as a heading. HTML in it is shown as text. */
export function ArticleContent({ content, sourceUrl: source }: { content: string; sourceUrl: string }) {
  const base = sourceUrl(source)
  // relative links belong to the source site; the app's own router uses the hash
  const resolve = (url: string) => sourceUrl(base && URL.canParse(url, base) ? new URL(url, base).href : url)?.replace(DOCS_MARKDOWN, '$1/')
  return (
    <section className="card pad">
      <h2 className="sec">Article</h2>
      {base && <p><a className="link" href={base} target="_blank" rel="noopener noreferrer">Read the original article</a></p>}
      <div className="md">
        <Markdown remarkPlugins={plugins} urlTransform={resolve} components={components}>{content.replace(/^\s*# .*\n+/, '')}</Markdown>
      </div>
    </section>
  )
}
