import assert from 'node:assert/strict'
import { after, before, beforeEach, test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

let vite, tickets, articles, users, profile, mutation, ArticleContent
const store = new Map()

before(async () => {
  globalThis.localStorage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) }
  vite = await createServer({ cacheDir: 'node_modules/.vite-test', server: { middlewareMode: true, watch: null, ws: false }, optimizeDeps: { noDiscovery: true, include: [] } })
  const load = (p) => vite.ssrLoadModule('/src/' + p)
  tickets = await load('shared/api/tickets.ts')
  articles = await load('shared/api/articles.ts')
  users = await load('shared/api/users.ts')
  profile = await load('shared/api/profile.ts')
  mutation = await load('features/cases/useTicketMutation.ts')
  ArticleContent = (await load('features/knowledge-base/ArticleContent.tsx')).ArticleContent
})
after(async () => vite?.close())
beforeEach(() => store.clear())

/** Records the request and answers with `body`. */
function stub(t, body = {}, status = 200) {
  const f = t.mock.method(globalThis, 'fetch', async () => Response.json(body, { status }))
  return () => {
    const [url, init = {}] = f.mock.calls[0].arguments
    const u = new URL(url)
    return { path: u.pathname + u.search, method: init.method ?? 'GET', headers: init.headers, body: init.body && JSON.parse(init.body) }
  }
}

test('requests carry the demo user for the selected role', async (t) => {
  const req = stub(t)
  await users.getMe()
  assert.equal(req().path, '/me')
  assert.equal(req().headers['X-Demo-User'], 'customer')
  users.switchDemoRole('agent')
  t.mock.restoreAll()
  const next = stub(t, [])
  await users.listAgents()
  assert.equal(next().path, '/agents')
  assert.equal(next().headers['X-Demo-User'], 'alex')
})

test('creating a case sends the consent the customer gave', async (t) => {
  const req = stub(t, { id: 'SC-1' }, 201)
  const input = { title: 'T', category: 'backup', severity: 'High', description: 'd', sources: [], consent: true }
  assert.deepEqual(await tickets.createTicket(input), { id: 'SC-1' })
  assert.deepEqual([req().method, req().path, req().body], ['POST', '/tickets', input])
})

test('unassigning sends an explicit null, and other patches leave the assignee out', async (t) => {
  let req = stub(t)
  await tickets.updateTicket('SC-1', { assignee: undefined })
  assert.deepEqual([req().method, req().path, req().body], ['PATCH', '/tickets/SC-1', { assignee: null }])
  t.mock.restoreAll()
  req = stub(t)
  await tickets.updateTicket('SC-1', { status: 'Resolved' })
  assert.deepEqual(req().body, { status: 'Resolved' })
})

test('take and reply use their endpoints; a customer reply has no status', async (t) => {
  let req = stub(t)
  await tickets.takeTicket('SC-1')
  assert.deepEqual([req().method, req().path], ['POST', '/tickets/SC-1/take'])
  t.mock.restoreAll()
  req = stub(t)
  await tickets.replyToTicket('SC-1', 'hi')
  assert.deepEqual([req().path, req().body], ['/tickets/SC-1/replies', { body: 'hi' }])
})

test('a 404 becomes null, every other failure throws', async (t) => {
  stub(t, {}, 404)
  assert.equal(await tickets.getTicket('SC-9'), null)
  assert.equal(await articles.getArticle('nope'), null)
  await assert.rejects(() => tickets.takeTicket('SC-9'), /404/)
  t.mock.restoreAll()
  stub(t, {}, 503)
  await assert.rejects(() => tickets.getTicket('SC-9'), /503/)
})

test('ids are escaped and /kb/search never reads the search endpoint as an article', async (t) => {
  const req = stub(t)
  await articles.getArticle('a/b?c')
  assert.equal(req().path, '/articles/a%2Fb%3Fc')
  assert.equal(await articles.getArticle('search'), null)
})

test('search sends the query and topic, within the API length limit', async (t) => {
  let req = stub(t, [])
  await articles.searchArticles('a & b', 'backup')
  assert.equal(req().path, '/articles/search?q=a+%26+b&topic=backup')
  t.mock.restoreAll()
  req = stub(t, [])
  await articles.searchArticles('x'.repeat(5000))
  assert.equal(new URL('http://h' + req().path).searchParams.get('q').length, 4000)
})

test('saving the profile PUTs the whole profile and returns what was stored', async (t) => {
  const p = { name: 'A', email: 'a@b.c', company: '', timezone: 'UTC', phone: '', notify: { replies: true, status: true, digest: false } }
  const req = stub(t, { ...p, name: 'Stored' })
  assert.equal((await profile.saveProfile(p)).name, 'Stored')
  assert.deepEqual([req().method, req().path, req().body], ['PUT', '/profile', p])
})

test('write failures explain conflicts and permissions', async () => {
  const { ApiError } = await vite.ssrLoadModule('/src/shared/api/client.ts')
  assert.match(mutation.failureText(new ApiError('', 409)), /changed/i)
  assert.match(mutation.failureText(new ApiError('', 403)), /not allowed|can’t/i)
  assert.match(mutation.failureText(new Error('network')), /try again/i)
})

const article = (content, sourceUrl = 'https://x.test/docs/a/') =>
  renderToStaticMarkup(createElement(ArticleContent, { content, sourceUrl }))

test('article markdown is formatted, without its repeated title', () => {
  const html = article('# Title\n\n**Bold**\n\n## Part\n\n- one\n\n```sh\n# a comment\n```\n\n# Second title\n')
  assert.match(html, /<strong>Bold<\/strong>/)
  assert.match(html, /<h2>Part<\/h2>/)
  assert.match(html, /<li>one<\/li>/)
  assert.match(html, /<pre><code[^>]*># a comment/)
  assert.doesNotMatch(html, />Title</)
  assert.match(html, /<h2>Second title<\/h2>/) // the page already has its h1
})

test('article tables are formatted inside a scrolling box', () => {
  assert.match(article('| A | B |\n| --- | --- |\n| 1 | 2 |\n'), /<div class="md-table"[^>]*><table>.*<td>1<\/td>/s)
})

test('HTML in an article is shown as text: placeholders survive and scripts do not run', () => {
  const html = article('Use <username> here <script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n')
  assert.match(html, /&lt;username&gt;/)
  assert.match(html, /&lt;script&gt;/)
  assert.match(html, /&lt;img src=x/)
  assert.doesNotMatch(html, /<script|<img|<username/)
})

test('article links open safely in a new tab and resolve against the source, not the app', () => {
  assert.match(article('[x](https://y.test/p)'), /<a href="https:\/\/y\.test\/p" target="_blank" rel="noopener noreferrer">x<\/a>/)
  assert.match(article('[x](../b)'), /href="https:\/\/x\.test\/docs\/b"/)
  assert.match(article('[x](#part)'), /href="https:\/\/x\.test\/docs\/a\/#part"/)
  assert.match(article('![d](/i.png)'), /<img src="https:\/\/x\.test\/i\.png" alt="d"/)
})

test('links to a docs page’s markdown file open its web page, keeping the anchor', () => {
  const href = (url) => article(`[x](${url})`).match(/href="([^"]*)" [^>]*>x</)[1]
  assert.equal(href('https://www.mongodb.com/docs/atlas/scale-cluster.md#std-label-modify-cluster'), 'https://www.mongodb.com/docs/atlas/scale-cluster/#std-label-modify-cluster')
  assert.equal(href('https://www.mongodb.com/docs/atlas/scale-cluster.md'), 'https://www.mongodb.com/docs/atlas/scale-cluster/')
  for (const url of ['https://github.com/a/b/README.md', 'https://www.mongodb.com/docs/a.md/b/', 'https://www.mongodb.com/blog/a.md', 'https://www.mongodb.com.evil.test/docs/a.md'])
    assert.equal(href(url), url)
})

test('unsafe article links become plain text', () => {
  for (const url of ['javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'data:text/html,x', 'vbscript:x']) {
    const html = article(`[click](${url}) ![pic](${url})`, url)
    assert.match(html, /click/)
    assert.match(html, /pic/)
    assert.doesNotMatch(html, /<a|<img|href|src=/)
  }
})
