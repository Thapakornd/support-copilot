import { QueryClient } from '@tanstack/react-query'
import { Outlet, createHashHistory, createRootRouteWithContext, createRoute, createRouter, redirect } from '@tanstack/react-router'
import { AccountPage } from '../pages/AccountPage'
import { ArticlePage } from '../pages/ArticlePage'
import { AskPage } from '../pages/AskPage'
import { CaseDetailPage } from '../pages/CaseDetailPage'
import { CasesPage } from '../pages/CasesPage'
import { HelpPage } from '../pages/HelpPage'
import { KnowledgeBasePage } from '../pages/KnowledgeBasePage'
import { NewCasePage } from '../pages/NewCasePage'
import { QueuePage } from '../pages/QueuePage'
import { q } from '../shared/api/queries'
import { NotFound } from '../shared/ui/NotFound'
import { Footer } from '../widgets/Footer'
import { Header } from '../widgets/Header/Header'

export const queryClient = new QueryClient()

const root = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  // the signed-in user gates every page, so load it before anything renders
  beforeLoad: ({ context }) => context.queryClient.ensureQueryData(q.me),
  component: () => (
    <>
      <Header />
      <main><Outlet /></main>
      <Footer />
    </>
  ),
  notFoundComponent: () => <NotFound title="Page not found" />,
  errorComponent: ({ error }) => <NotFound title={`Something went wrong: ${error instanceof Error ? error.message : String(error)}`} />,
})

const route = <P extends string>(path: P) => ({ getParentRoute: () => root, path })

const home = createRoute({
  ...route('/'),
  beforeLoad: async ({ context }) => {
    const me = await context.queryClient.ensureQueryData(q.me)
    throw redirect({ to: me.role === 'agent' ? '/queue' : '/help' })
  },
})

// UX only: hides agent pages from customers. The backend must enforce roles on every endpoint.
const agentOnly = async ({ context }: { context: { queryClient: QueryClient } }) => {
  const me = await context.queryClient.ensureQueryData(q.me)
  if (me.role !== 'agent') throw redirect({ to: '/help' })
}

const help = createRoute({ ...route('/help'), component: HelpPage })
const ask = createRoute({
  ...route('/help/$category'),
  loader: ({ context }) => context.queryClient.ensureQueryData(q.articles),
  component: AskPage,
  remountDeps: ({ params }) => params.category,
})
const kb = createRoute({
  ...route('/kb'),
  loader: ({ context }) => context.queryClient.ensureQueryData(q.articles),
  component: KnowledgeBasePage,
})
const article = createRoute({
  ...route('/kb/$articleId'),
  loader: ({ context, params }) => Promise.all([
    context.queryClient.ensureQueryData(q.article(params.articleId)),
    context.queryClient.ensureQueryData(q.articles),
  ]),
  component: ArticlePage,
  remountDeps: ({ params }) => params.articleId,
})
const queue = createRoute({
  ...route('/queue'),
  beforeLoad: agentOnly,
  loader: ({ context }) => context.queryClient.ensureQueryData(q.tickets),
  component: QueuePage,
})
const cases = createRoute({
  ...route('/cases'),
  loader: ({ context }) => context.queryClient.ensureQueryData(q.tickets),
  component: CasesPage,
})
const caseDetail = createRoute({
  ...route('/cases/$caseId'),
  loader: ({ context, params }) => Promise.all([
    context.queryClient.ensureQueryData(q.ticket(params.caseId)),
    context.queryClient.ensureQueryData(q.agents),
  ]),
  component: CaseDetailPage,
  remountDeps: ({ params }) => params.caseId,
})
const newCase = createRoute({ ...route('/case'), component: NewCasePage })
const account = createRoute({
  ...route('/account'),
  beforeLoad: () => { throw redirect({ to: '/account/$tab', params: { tab: 'profile' } }) },
})
const accountTab = createRoute({
  ...route('/account/$tab'),
  loader: ({ context }) => context.queryClient.ensureQueryData(q.profile),
  component: AccountPage,
})

export const router = createRouter({
  routeTree: root.addChildren([home, help, ask, kb, article, queue, cases, caseDetail, newCase, account, accountTab]),
  // ponytail: hash URLs keep the old links working and need no server rewrite rules; switch to browser history when deployed behind one.
  history: createHashHistory(),
  context: { queryClient },
  defaultPreload: 'intent',
  // loaders only warm the Query cache; Query decides freshness
  defaultPreloadStaleTime: 0,
  scrollRestoration: true,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
