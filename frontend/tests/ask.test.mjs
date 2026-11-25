import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

let vite
let submitQuestion
let AnswerPanel

before(async () => {
  vite = await createServer({ cacheDir: 'node_modules/.vite-test', server: { middlewareMode: true, watch: null, ws: false }, optimizeDeps: { noDiscovery: true, include: [] } })
  const ask = await vite.ssrLoadModule('/src/features/assistant/useAsk.ts')
  const panel = await vite.ssrLoadModule('/src/features/assistant/AnswerPanel.tsx')
  submitQuestion = ask.submitQuestion
  AnswerPanel = panel.AnswerPanel
})

after(async () => vite?.close())

const sources = ['Zebra', 'Alpha', 'Beta', 'Last'].map((title, i) => ({
  number: i + 1,
  document_id: 'doc-' + i,
  revision_id: 'revision-' + i,
  chunk_set_id: 'set-' + i,
  chunk_id: 'chunk-' + i,
  title,
  heading_path: ['Section ' + i],
  source_url: i === 3 ? 'javascript:alert(1)' : 'https://example.com/ref/' + i,
}))
const answer = { answer: 'Check the route [1].', status: 'answered', sources }

test('Ask sends the canonical category and preserves citations returned by chat', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json(answer))
  const result = await submitQuestion('timeout', 'connectivity')
  assert.deepEqual(JSON.parse(fetch.mock.calls[0].arguments[1].body), {
    question: 'timeout', category: 'connectivity',
  })
  assert.deepEqual(result, { question: 'timeout', ...answer })
})

test('Ask propagates an API failure so the page can show retry', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(null, { status: 503 }))
  await assert.rejects(() => submitQuestion('timeout'), /503/)
})

test('Answer panel shows every source in API order and only links safe URLs', () => {
  const html = renderToStaticMarkup(createElement(AnswerPanel, {
    res: { question: 'timeout', ...answer },
  }))
  assert.match(html, /Zebra.*Alpha.*Beta.*Last/)
  assert.match(html, /href="https:\/\/example\.com\/ref\/0"/)
  assert.doesNotMatch(html, /href="[^"]*(?:javascript|alert)/)
})

test('Answer panel shows the clarifying question without a references list', () => {
  const html = renderToStaticMarkup(createElement(AnswerPanel, {
    res: { question: 'timeout', answer: 'What error did you see?', status: 'insufficient_evidence', sources: [] },
  }))
  assert.match(html, /More detail needed.*What error did you see\?/)
  assert.doesNotMatch(html, /Referenced articles/)
})
